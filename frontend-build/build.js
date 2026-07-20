// Build local dos assets de front-end do SCA.
//
// Antes, o app carregava em toda requisição, de servidores de terceiros:
//   - cdn.tailwindcss.com     -> compilador Tailwind INTEIRO rodando no
//                                navegador, recompilando o CSS a cada
//                                carregamento de página (o maior peso).
//   - cdn.jsdelivr.net        -> Alpine.js
//   - cdnjs.cloudflare.com    -> Font Awesome
//   - fonts.googleapis.com/   -> Google Fonts (Inter, JetBrains Mono)
//     fonts.gstatic.com
//
// Isso significa: 5 domínios externos, várias requisições extras, e um
// compilador CSS rodando no navegador de cada visitante. Este script
// resolve tudo isso gerando arquivos ESTÁTICOS locais (rode `npm run
// build` sempre que mudar classes Tailwind nos templates ou no app.js):
//   app/static/css/tailwind.css   <- CSS já compilado, só com as classes
//                                     realmente usadas (bem menor que a
//                                     folha completa do Tailwind)
//   app/static/js/vendor/alpine.min.js
//   app/static/vendor/fontawesome/...
//   app/static/fonts/... (+ fonts.css com @font-face local)
//
// O Flask então serve tudo isso como arquivo estático comum: mesmo
// domínio, cacheável, sem esperar terceiros, sem JIT no navegador.
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const APP_STATIC = path.resolve(__dirname, "../app/static");

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

console.log("→ Compilando Tailwind (produção, minificado, só classes usadas)...");
execSync(
  `npx tailwindcss -c tailwind.config.js -i tailwind.entry.css -o "${APP_STATIC}/css/tailwind.css" --minify`,
  { cwd: __dirname, stdio: "inherit" }
);

console.log("→ Copiando Alpine.js (build de produção, minificado)...");
fs.mkdirSync(`${APP_STATIC}/js/vendor`, { recursive: true });
fs.copyFileSync(
  require.resolve("alpinejs/dist/cdn.min.js"),
  `${APP_STATIC}/js/vendor/alpine.min.js`
);

console.log("→ Copiando Font Awesome (CSS + webfonts, só solid/regular)...");
const faPkgDir = path.dirname(require.resolve("@fortawesome/fontawesome-free/package.json"));
copyDir(path.join(faPkgDir, "css"), `${APP_STATIC}/vendor/fontawesome/css`);
copyDir(path.join(faPkgDir, "webfonts"), `${APP_STATIC}/vendor/fontawesome/webfonts`);
// O projeto só usa os estilos "fa-solid" e "fa-regular" (ver
// autocomplete de classes nos templates) — "fontawesome.min.css" é o
// arquivo BASE com o mapeamento nome-do-ícone -> glifo, e precisa ficar;
// "solid.min.css"/"regular.min.css" completam com a fonte de cada
// estilo. O resto (all.min.css, brands, v4-shims, duotone/sharp) nunca é
// usado neste app — mantê-los só custaria download/parse à toa.
const cssManter = new Set(["fontawesome.min.css", "solid.min.css", "regular.min.css"]);
for (const f of fs.readdirSync(`${APP_STATIC}/vendor/fontawesome/css`)) {
  if (!cssManter.has(f)) fs.unlinkSync(`${APP_STATIC}/vendor/fontawesome/css/${f}`);
}
const webfontsManter = new Set(["fa-solid-900.woff2", "fa-regular-400.woff2"]);
for (const f of fs.readdirSync(`${APP_STATIC}/vendor/fontawesome/webfonts`)) {
  if (!webfontsManter.has(f)) fs.unlinkSync(`${APP_STATIC}/vendor/fontawesome/webfonts/${f}`);
}

console.log("→ Copiando fontes (Inter + JetBrains Mono, só os pesos usados)...");
const fontsOut = `${APP_STATIC}/fonts`;
fs.mkdirSync(fontsOut, { recursive: true });
const interDir = path.dirname(require.resolve("@fontsource/inter/index.css"));
const jbmDir = path.dirname(require.resolve("@fontsource/jetbrains-mono/index.css"));
const interPesos = ["400", "500", "600", "700", "800"];
const jbmPesos = ["500", "600"];
let fontsCss = "/* Gerado por build.js — Inter + JetBrains Mono self-hosted (ver npm run build) */\n";
for (const w of interPesos) {
  const file = `inter-latin-${w}-normal.woff2`;
  fs.copyFileSync(path.join(interDir, "files", file), path.join(fontsOut, file));
  fontsCss += `@font-face{font-family:'Inter';font-style:normal;font-weight:${w};font-display:swap;src:url('/static/fonts/${file}') format('woff2');}\n`;
}
for (const w of jbmPesos) {
  const file = `jetbrains-mono-latin-${w}-normal.woff2`;
  fs.copyFileSync(path.join(jbmDir, "files", file), path.join(fontsOut, file));
  fontsCss += `@font-face{font-family:'JetBrains Mono';font-style:normal;font-weight:${w};font-display:swap;src:url('/static/fonts/${file}') format('woff2');}\n`;
}
fs.writeFileSync(path.join(fontsOut, "fonts.css"), fontsCss);

console.log("✔ Build concluído — app/static agora tem todos os assets localmente.");
