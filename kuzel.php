<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Výpočet komolého kužele</title>
</head>
<body>
    <h1>Výpočet komolého kužele</h1>
    <p>Zadejte průměry obou podstav a výšku komolého kužele:</p>

    <!-- Formulář odesílá data sám sobě (action="" znamená aktuální soubor) -->
    <form action="" method="post">
        <label for="d1">Průměr první podstavy (d1):</label><br>
        <input type="number" step="any" id="d1" name="d1" required><br><br>

        <label for="d2">Průměr druhé podstavy (d2):</label><br>
        <input type="number" step="any" id="d2" name="d2" required><br><br>

        <label for="h">Výška kužele (h):</label><br>
        <input type="number" step="any" id="h" name="h" required><br><br>

        <!-- Tlačítko pro odeslání. Má name="vypocitat", abychom poznali, že bylo kliknuto -->
        <input type="submit" name="vypocitat" value="Vypočítat">
    </form>

    <?php
    // KONTROLA: Spuštěno poprvé, nebo po kliknutí na tlačítko?
    // isset($_POST['vypocitat']) zjistí, zda uživatel už odeslal formulář
    if (isset($_POST['vypocitat'])) {

        // 1. KROK: Načtení hodnot z formuláře
        $d1 = $_POST['d1'];
        $d2 = $_POST['d2'];
        $h  = $_POST['h'];

        // 2. KROK: Převod průměrů na poloměry (r = d / 2)
        $r1 = $d1 / 2;
        $r2 = $d2 / 2;

        // 3. KROK: Výpočet strany kužele (s) pomocí Pythagorovy věty
        // sqrt() = druhá odmocnina, pow(x, 2) = mocnina na druhou
        $s = sqrt(pow($h, 2) + pow($r1 - $r2, 2));

        // 4. KROK: Výpočet objemu komolého kužele
        // V = 1/3 * pi * h * (r1^2 + r1*r2 + r2^2)
        $objem = (1 / 3) * pi() * $h * ($r1 * $r1 + $r1 * $r2 + $r2 * $r2);

        // 5. KROK: Výpočet povrchu komolého kužele
        // S = pi*r1^2 + pi*r2^2 + pi*(r1+r2)*s
        $povrch = pi() * pow($r1, 2) + pi() * pow($r2, 2) + pi() * ($r1 + $r2) * $s;

        // 6. KROK: Výpis výsledků pod formulář
        echo "<hr>";
        echo "<h2>Výsledky:</h2>";
        echo "<p>Objem (V): <strong>" . round($objem, 2) . "</strong></p>";
        echo "<p>Povrch (S): <strong>" . round($povrch, 2) . "</strong></p>";
    }
    ?>
</body>
</html>
