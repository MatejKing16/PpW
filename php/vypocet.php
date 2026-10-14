<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Výsledky výpočtu komolého kužele</title>
</head>
<body>
    <h1>Výsledky výpočtu komolého kužele</h1>

    <?php
    // KROK 1: PŘEVZETÍ HODNOT Z FORMULÁŘE
    // Hodnoty z formuláře se přenesou v poli $_POST podle názvů v atributu name (d1, d2, h)
    $d1 = $_POST['d1'];
    $d2 = $_POST['d2'];
    $h  = $_POST['h'];

    // KROK 2: PŘEVOD PRŮMĚRŮ NA POLOMĚRY (r = d / 2)
    $r1 = $d1 / 2;
    $r2 = $d2 / 2;

    // KROK 3: VÝPOČET STRANY KUŽELE (s)
    // Pomocí Pythagorovy věty: s = odmocnina z (h^2 + (r1 - r2)^2)
    // sqrt() = druhá odmocnina, pow(x, 2) = mocnina na druhou
    $s = sqrt(pow($h, 2) + pow($r1 - $r2, 2));

    // KROK 4: VÝPOČET OBJEMU (V)
    // Vzorec: V = 1/3 * pi * h * (r1^2 + r1*r2 + r2^2)
    // pi() = matematická konstanta pí (3.14159...)
    $objem = (1 / 3) * pi() * $h * ($r1 * $r1 + $r1 * $r2 + $r2 * $r2);

    // KROK 5: VÝPOČET POVRCHU (S)
    // Sčítáme dolní podstavu + horní podstavu + plášť
    // Vzorec: S = pi*r1^2 + pi*r2^2 + pi*(r1+r2)*s
    $povrch = pi() * pow($r1, 2) + pi() * pow($r2, 2) + pi() * ($r1 + $r2) * $s;

    // KROK 6: VÝPIS VÝSLEDKŮ NA STRÁNKU
    // round($cislo, 2) zaokrouhlí hodnotu na 2 desetinná místa
    echo "<p>Zadaný průměr první podstavy (d1): <strong>" . $d1 . "</strong></p>";
    echo "<p>Zadaný průměr druhé podstavy (d2): <strong>" . $d2 . "</strong></p>";
    echo "<p>Zadaná výška kužele (h): <strong>" . $h . "</strong></p>";
    echo "<hr>";
    echo "<p>Vypočtený objem (V): <strong>" . round($objem, 2) . "</strong></p>";
    echo "<p>Vypočtený povrch (S): <strong>" . round($povrch, 2) . "</strong></p>";
    ?>

    <br>
    <!-- Odkaz zpět na zadávací formulář -->
    <a href="formular.html">Zpět na zadání</a>
</body>
</html>
