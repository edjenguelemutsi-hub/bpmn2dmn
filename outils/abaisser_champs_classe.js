// abaisser_champs_classe.js — rend les bibliothèques de ui/lib lisibles par
// les navigateurs antérieurs à 2021 (Safari 11.1 à 14.0 notamment).
//
// dmn-js est distribué avec des champs de classe (syntaxe ECMAScript 2022 :
// `static $inject = [...]`, `_viewsChanged = () => {...}`), que Safari ne
// comprend qu'à partir de la version 14.1. Un seul de ces champs suffit à
// faire rejeter le fichier entier, et la page reste alors sans réaction.
// Ce script réécrit chaque champ, à partir de l'arbre syntaxique d'acorn :
//   - champ statique  -> accesseur statique `static get cle(){return valeur}`
//   - champ d'instance -> affectation `this.cle = valeur` en tête du
//     constructeur (juste après super() pour une classe dérivée), dans
//     l'ordre de déclaration ; le constructeur est créé s'il manque.
// Le résultat doit s'analyser en ECMAScript 2018, ce que le script vérifie.
//
// Utilisation (Node.js et le paquet acorn, par exemple `npm install acorn`) :
//     node outils/abaisser_champs_classe.js ui/lib/dmn-navigated-viewer.min.js
// À rejouer après toute mise à jour des bibliothèques de ui/lib ; le test
// tests/test_robustesse.py (TestCompatibiliteNavigateurs) veille à ce
// qu'aucun champ de classe ne subsiste.
const fs = require("fs");
const acorn = require("acorn");
const chemin = process.argv[2];
let code = fs.readFileSync(chemin, "utf8");

function* parcourir(n) {
  if (!n || typeof n.type !== "string") return;
  yield n;
  for (const k of Object.keys(n)) {
    const v = n[k];
    if (Array.isArray(v)) { for (const x of v) if (x && typeof x.type === "string") yield* parcourir(x); }
    else if (v && typeof v.type === "string") yield* parcourir(v);
  }
}

function cle(champ) {
  const k = champ.key;
  if (champ.computed) return "this[" + code.slice(k.start, k.end) + "]";
  if (k.type === "Identifier") return "this." + k.name;
  return "this[" + code.slice(k.start, k.end) + "]";
}

let passe = 0, total = 0;
for (;;) {
  const ast = acorn.parse(code, { ecmaVersion: 2022, sourceType: "script" });
  const corps = [...parcourir(ast)].filter(n => n.type === "ClassBody" &&
    n.body.some(m => m.type === "PropertyDefinition"));
  if (!corps.length) break;
  passe++;
  // classes dont les valeurs de champs ne contiennent pas d'autres champs
  const feuilles = corps.filter(c => !c.body.some(m => m.type === "PropertyDefinition" && m.value &&
    [...parcourir(m.value)].some(x => x.type === "PropertyDefinition")));
  const edits = [];  // {debut, fin, texte}
  for (const c of feuilles) {
    const champs = c.body.filter(m => m.type === "PropertyDefinition");
    const ctor = c.body.find(m => m.type === "MethodDefinition" && m.kind === "constructor");
    const classe = [...parcourir(ast)].find(n => (n.type === "ClassDeclaration" || n.type === "ClassExpression") && n.body === c);
    const statiques = champs.filter(m => m.static), instances = champs.filter(m => !m.static);
    // champ statique -> accesseur statique (ES2015), même valeur lue par
    // Classe.cle ; sans valeur, l'accesseur rend undefined
    for (const m of statiques) {
      let fin = m.end;
      if (code[fin] === ";") fin++;
      const k = m.computed ? "[" + code.slice(m.key.start, m.key.end) + "]" : code.slice(m.key.start, m.key.end);
      const v = m.value ? code.slice(m.value.start, m.value.end) : "void 0";
      const sep = /^[\[({"'`]/.test(v) ? "" : " ";   // `return[` est valide
      edits.push({ debut: m.start, fin, texte: "static get " + k + "(){return" + sep + v + "}" });
    }
    total += statiques.length;
    const init = instances.map(m => cle(m) + "=" + (m.value ? code.slice(m.value.start, m.value.end) : "void 0")).join(";") + ";";
    for (const m of instances) {
      let fin = m.end;
      if (code[fin] === ";") fin++;
      edits.push({ debut: m.start, fin, texte: "" });
    }
    if (!instances.length) {
      // rien à placer dans le constructeur
    } else if (ctor) {
      const corpsCtor = ctor.value.body;      // BlockStatement
      const premier = corpsCtor.body[0];
      const estSuper = e => e && e.type === "CallExpression" && e.callee.type === "Super";
      if (classe.superClass && premier && premier.type === "ExpressionStatement" && estSuper(premier.expression)) {
        edits.push({ debut: premier.end, fin: premier.end, texte: init });
      } else if (classe.superClass && premier && premier.type === "ExpressionStatement" &&
                 premier.expression.type === "SequenceExpression" && estSuper(premier.expression.expressions[0])) {
        const s = premier.expression.expressions[0];
        const enSequence = instances.map(m => "(" + cle(m) + "=" + (m.value ? code.slice(m.value.start, m.value.end) : "void 0") + ")").join(",");
        edits.push({ debut: s.end, fin: s.end, texte: "," + enSequence });
      } else if (classe.superClass) {
        throw new Error("constructeur dérivé sans super() en tête à " + ctor.start);
      } else {
        edits.push({ debut: corpsCtor.start + 1, fin: corpsCtor.start + 1, texte: init });
      }
    } else {
      const ctorTexte = classe.superClass ? "constructor(...a){super(...a);" + init + "}" : "constructor(){" + init + "}";
      edits.push({ debut: c.start + 1, fin: c.start + 1, texte: ctorTexte });
    }
    total += instances.length;
  }
  edits.sort((a, b) => b.debut - a.debut || b.fin - a.fin);
  for (const e of edits) code = code.slice(0, e.debut) + e.texte + code.slice(e.fin);
}
acorn.parse(code, { ecmaVersion: 2018, sourceType: "script" });   // doit passer
fs.writeFileSync(chemin, code);
console.log("champs de classe réécrits : " + total + " (en " + passe + " passe(s)) ; analyse ES2018 : OK");
