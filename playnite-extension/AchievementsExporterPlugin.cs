using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows.Controls;
using Playnite.SDK;
using Playnite.SDK.Events;
using Playnite.SDK.Plugins;

namespace AchievementsExporter
{
    /// <summary>
    /// A la fermeture d'un jeu : exporte les temps de jeu connus de Playnite,
    /// puis declenche l'extracteur de succes.
    ///
    /// Playnite est la meilleure source de temps de jeu du poste : il compte
    /// aussi les parties lancees hors Steam, la ou Steam ne voit que ce qui
    /// passe par son client.
    /// </summary>
    public class AchievementsExporterPlugin : GenericPlugin
    {
        // Identifiant du plugin de bibliotheque Steam de Playnite : c'est lui
        // qui garantit que GameId contient bien un appid Steam.
        private static readonly Guid SteamLibraryPluginId =
            Guid.Parse("CB91DFC9-B977-43BF-8E70-55F46E410FAB");

        private static readonly ILogger Journal = LogManager.GetLogger();

        private readonly ExporterSettingsViewModel reglages;

        public override Guid Id { get; } = Guid.Parse("7b1f9c2e-4d3a-4a1b-9e6f-0c5a8d2b6e41");

        public AchievementsExporterPlugin(IPlayniteAPI api) : base(api)
        {
            reglages = new ExporterSettingsViewModel(this);
            Properties = new GenericPluginProperties { HasSettings = true };
        }

        public override ISettings GetSettings(bool firstRunSettings) => reglages;

        public override UserControl GetSettingsView(bool firstRunView) =>
            new ExporterSettingsView(reglages.Settings);

        public override void OnGameStopped(OnGameStoppedEventArgs args)
        {
            var config = reglages.Settings;
            if (!config.Enabled)
            {
                return;
            }

            try
            {
                var chemin = EcrireExportTempsDeJeu(config);
                LancerExtracteur(config, chemin);
            }
            catch (Exception erreur)
            {
                // Un echec ici ne doit jamais perturber Playnite : on journalise
                // et, si l'utilisateur l'a demande, on le signale discretement.
                Journal.Error(erreur, "Echec de l'export des succes apres la fermeture du jeu.");
                if (config.NotifyOnError)
                {
                    PlayniteApi.Notifications.Add(new NotificationMessage(
                        "achievements-exporter-erreur",
                        "Export des succes : " + erreur.Message,
                        NotificationType.Error));
                }
            }
        }

        /// <summary>
        /// Ecrit le JSON des temps de jeu et retourne son chemin.
        /// Ecriture atomique : l'extracteur ne peut jamais lire un fichier
        /// a moitie ecrit.
        /// </summary>
        private string EcrireExportTempsDeJeu(ExporterSettings config)
        {
            var chemin = string.IsNullOrWhiteSpace(config.PlaytimeFilePath)
                ? Path.Combine(GetPluginUserDataPath(), "playnite_playtime.json")
                : config.PlaytimeFilePath;
            Directory.CreateDirectory(Path.GetDirectoryName(chemin));

            var apparies = new List<string>();
            var orphelins = new List<string>();

            foreach (var jeu in PlayniteApi.Database.Games)
            {
                if (jeu.Playtime <= 0)
                {
                    continue;
                }

                // Playtime est en secondes cote Playnite, en minutes cote outil.
                var minutes = (long)(jeu.Playtime / 60);
                var derniere = jeu.LastActivity.HasValue
                    ? Quote(jeu.LastActivity.Value.ToUniversalTime()
                        .ToString("yyyy-MM-ddTHH:mm:ssK", CultureInfo.InvariantCulture))
                    : "null";

                if (jeu.PluginId == SteamLibraryPluginId && EstAppidValide(jeu.GameId))
                {
                    apparies.Add(string.Format(
                        CultureInfo.InvariantCulture,
                        "    {0}: {{\"name\": {1}, \"playtime_minutes\": {2}, \"last_played\": {3}}}",
                        Quote(jeu.GameId), Quote(jeu.Name), minutes, derniere));
                }
                else
                {
                    // Jeux sans appid Steam (ajoutes a la main, autres launchers) :
                    // conserves a titre indicatif, l'outil ne sait pas les relier
                    // a des succes Steam.
                    orphelins.Add(string.Format(
                        CultureInfo.InvariantCulture,
                        "    {{\"name\": {0}, \"playtime_minutes\": {1}}}",
                        Quote(jeu.Name), minutes));
                }
            }

            var json = new StringBuilder();
            json.AppendLine("{");
            json.AppendLine("  \"generated_at\": " + Quote(
                DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssK", CultureInfo.InvariantCulture)) + ",");
            json.AppendLine("  \"games\": {");
            json.AppendLine(string.Join("," + Environment.NewLine, apparies));
            json.AppendLine("  },");
            json.AppendLine("  \"unmatched\": [");
            json.AppendLine(string.Join("," + Environment.NewLine, orphelins));
            json.AppendLine("  ]");
            json.Append("}");

            var temporaire = chemin + ".tmp";
            File.WriteAllText(temporaire, json.ToString(), new UTF8Encoding(false));
            if (File.Exists(chemin))
            {
                File.Delete(chemin);
            }
            File.Move(temporaire, chemin);

            Journal.Info(string.Format(CultureInfo.InvariantCulture,
                "Temps de jeu exportes : {0} jeux Steam, {1} sans appid.",
                apparies.Count, orphelins.Count));
            return chemin;
        }

        private void LancerExtracteur(ExporterSettings config, string cheminTempsDeJeu)
        {
            if (string.IsNullOrWhiteSpace(config.PythonPath)
                || string.IsNullOrWhiteSpace(config.OutputDirectory))
            {
                Journal.Warn("Extracteur non lance : chemin Python ou dossier de sortie non configure.");
                return;
            }

            var arguments = string.Format(
                CultureInfo.InvariantCulture,
                "-m extractor --output-dir \"{0}\" --playnite \"{1}\"",
                config.OutputDirectory.TrimEnd('\\'), cheminTempsDeJeu);

            var demarrage = new ProcessStartInfo
            {
                FileName = config.PythonPath,
                Arguments = arguments,
                WorkingDirectory = config.ExtractorDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
            };

            Journal.Info("Lancement de l'extracteur : " + config.PythonPath + " " + arguments);
            Process.Start(demarrage);
        }

        private static bool EstAppidValide(string gameId) =>
            !string.IsNullOrWhiteSpace(gameId) && gameId.All(char.IsDigit);

        /// <summary>Echappe une chaine pour l'inserer dans du JSON.</summary>
        private static string Quote(string valeur)
        {
            if (valeur == null)
            {
                return "null";
            }

            var sortie = new StringBuilder("\"");
            foreach (var c in valeur)
            {
                switch (c)
                {
                    case '"': sortie.Append("\\\""); break;
                    case '\\': sortie.Append("\\\\"); break;
                    case '\n': sortie.Append("\\n"); break;
                    case '\r': sortie.Append("\\r"); break;
                    case '\t': sortie.Append("\\t"); break;
                    default:
                        if (c < 0x20)
                        {
                            sortie.Append("\\u")
                                  .Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        }
                        else
                        {
                            sortie.Append(c);
                        }
                        break;
                }
            }
            return sortie.Append('"').ToString();
        }
    }
}
