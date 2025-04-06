from ShowRenamer import ShowRenamer

# Initialisiere ShowRenamer (ohne API-Key, da wir nur Patterns testen)
renamer = ShowRenamer(api_key="dummy", interactive=True)

# Beispieldatei
filename = "Invincible.Unbesiegbar.S03E01.Jetzt.lachst.du.nicht.mehr.German.DL.AmazonHD.x264-4SF.mkv"

print("Willkommen zum Pattern-Demo!")
print("\nWir werden ein Pattern für diese Datei erstellen:", filename)
print("\nFolgen Sie den Anweisungen, um die Teile des Dateinamens zu markieren.")
print("Tipp: Für diese Datei könnten Sie z.B. markieren:")
print("[name].S[s]E[e].Jetzt.lachst.du.nicht.mehr.German.DL.AmazonHD.x264-4SF.mkv")

# Starte die interaktive Pattern-Erstellung
new_pattern = renamer.create_pattern_interactive(filename)

if new_pattern:
    print("\nErfolgreich! Das neue Pattern wurde zur Konfiguration hinzugefügt.")
    print("Sie können jetzt das Programm normal verwenden, um die Dateien umzubenennen.")
