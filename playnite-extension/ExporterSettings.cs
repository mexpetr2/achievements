using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using Playnite.SDK;
using Playnite.SDK.Data;

namespace AchievementsExporter
{
    /// <summary>Reglages persistes par Playnite pour cette extension.</summary>
    public class ExporterSettings : ObservableObject
    {
        private bool enabled = true;
        private string pythonPath = string.Empty;
        private string extractorDirectory = string.Empty;
        private string outputDirectory = string.Empty;
        private string playtimeFilePath = string.Empty;
        private bool notifyOnError = true;

        /// <summary>Declencher l'export a la fermeture d'un jeu.</summary>
        public bool Enabled { get => enabled; set => SetValue(ref enabled, value); }

        /// <summary>Interpreteur Python, typiquement le python.exe du venv.</summary>
        public string PythonPath { get => pythonPath; set => SetValue(ref pythonPath, value); }

        /// <summary>Dossier depuis lequel lancer `-m extractor`.</summary>
        public string ExtractorDirectory
        {
            get => extractorDirectory;
            set => SetValue(ref extractorDirectory, value);
        }

        /// <summary>Dossier partage surveille par l'appli web du NAS.</summary>
        public string OutputDirectory
        {
            get => outputDirectory;
            set => SetValue(ref outputDirectory, value);
        }

        /// <summary>Ou ecrire le JSON des temps de jeu (vide = dossier du plugin).</summary>
        public string PlaytimeFilePath
        {
            get => playtimeFilePath;
            set => SetValue(ref playtimeFilePath, value);
        }

        /// <summary>Afficher une notification Playnite en cas d'echec.</summary>
        public bool NotifyOnError
        {
            get => notifyOnError;
            set => SetValue(ref notifyOnError, value);
        }
    }

    /// <summary>Fait le lien entre les reglages et le stockage de Playnite.</summary>
    public class ExporterSettingsViewModel : ObservableObject, ISettings
    {
        private readonly AchievementsExporterPlugin plugin;
        private ExporterSettings avantEdition;

        public ExporterSettings Settings { get; set; }

        public ExporterSettingsViewModel(AchievementsExporterPlugin plugin)
        {
            this.plugin = plugin;
            Settings = plugin.LoadPluginSettings<ExporterSettings>() ?? new ExporterSettings();
        }

        public void BeginEdit()
        {
            // Copie de securite pour pouvoir annuler proprement.
            avantEdition = Serialization.GetClone(Settings);
        }

        public void CancelEdit()
        {
            Settings = avantEdition;
            OnPropertyChanged(nameof(Settings));
        }

        public void EndEdit()
        {
            plugin.SavePluginSettings(Settings);
        }

        public bool VerifySettings(out List<string> errors)
        {
            errors = new List<string>();

            if (!Settings.Enabled)
            {
                return true;
            }

            if (string.IsNullOrWhiteSpace(Settings.PythonPath))
            {
                errors.Add("Indiquez le chemin de python.exe.");
            }
            else if (!System.IO.File.Exists(Settings.PythonPath))
            {
                errors.Add("python.exe est introuvable : " + Settings.PythonPath);
            }

            if (string.IsNullOrWhiteSpace(Settings.ExtractorDirectory))
            {
                errors.Add("Indiquez le dossier du projet contenant l'extracteur.");
            }
            else if (!System.IO.Directory.Exists(Settings.ExtractorDirectory))
            {
                errors.Add("Dossier de l'extracteur introuvable : " + Settings.ExtractorDirectory);
            }

            if (string.IsNullOrWhiteSpace(Settings.OutputDirectory))
            {
                errors.Add("Indiquez le dossier partage de destination.");
            }

            return errors.Count == 0;
        }
    }

    /// <summary>
    /// Fenetre de reglages, construite en code plutot qu'en XAML : cela evite
    /// les cibles de compilation WPF de Visual Studio, absentes ici.
    /// </summary>
    public class ExporterSettingsView : UserControl
    {
        // Playnite affecte lui-meme le DataContext de cette vue : il y place
        // l'objet ISettings rendu par GetSettings(), c'est-a-dire le
        // view-model. Les liaisons doivent donc passer par sa propriete
        // Settings ("Settings.PythonPath") et non viser la propriete
        // directement, sinon elles echouent en silence : le texte saisi reste
        // affiche mais n'atteint jamais le modele.
        private const string Racine = nameof(ExporterSettingsViewModel.Settings) + ".";

        public ExporterSettingsView(ExporterSettingsViewModel viewModel)
        {
            DataContext = viewModel;

            var pile = new StackPanel { Margin = new Thickness(12) };

            pile.Children.Add(Case(
                "Exporter automatiquement a la fermeture d'un jeu",
                nameof(ExporterSettings.Enabled)));

            pile.Children.Add(Champ(
                "Chemin de python.exe",
                "Par exemple : S:\\Achievements\\.venv\\Scripts\\python.exe",
                nameof(ExporterSettings.PythonPath)));

            pile.Children.Add(Champ(
                "Dossier du projet",
                "Dossier contenant le module extractor. Par exemple : S:\\Achievements",
                nameof(ExporterSettings.ExtractorDirectory)));

            pile.Children.Add(Champ(
                "Dossier partage de destination",
                "Dossier surveille par l'appli web. Par exemple : \\\\NAS\\partage\\succes",
                nameof(ExporterSettings.OutputDirectory)));

            pile.Children.Add(Champ(
                "Fichier des temps de jeu (optionnel)",
                "Laisser vide pour utiliser le dossier de donnees du plugin.",
                nameof(ExporterSettings.PlaytimeFilePath)));

            pile.Children.Add(Case(
                "Me notifier en cas d'echec",
                nameof(ExporterSettings.NotifyOnError)));

            Content = new ScrollViewer
            {
                Content = pile,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            };
        }

        private static UIElement Champ(string libelle, string aide, string nomPropriete)
        {
            var propriete = Racine + nomPropriete;
            var bloc = new StackPanel { Margin = new Thickness(0, 0, 0, 12) };
            bloc.Children.Add(new TextBlock
            {
                Text = libelle,
                FontWeight = FontWeights.SemiBold,
                Margin = new Thickness(0, 0, 0, 2),
            });
            bloc.Children.Add(new TextBlock
            {
                Text = aide,
                Opacity = 0.7,
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 0, 0, 4),
            });

            var saisie = new TextBox();
            saisie.SetBinding(TextBox.TextProperty, new Binding(propriete)
            {
                UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged,
            });
            bloc.Children.Add(saisie);
            return bloc;
        }

        private static UIElement Case(string libelle, string nomPropriete)
        {
            var coche = new CheckBox
            {
                Content = libelle,
                Margin = new Thickness(0, 0, 0, 12),
            };
            coche.SetBinding(CheckBox.IsCheckedProperty, new Binding(Racine + nomPropriete));
            return coche;
        }
    }
}
