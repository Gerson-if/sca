/** Config do build estático do Tailwind (ver README seção "Build de assets").
 * Escaneia os templates/JS reais do app para gerar só o CSS realmente
 * usado — ao contrário do script CDN (cdn.tailwindcss.com), que embarcava
 * o compilador inteiro no navegador e recompilava a cada carregamento de
 * página. Isso é o que fica pesado/lento com um app deste tamanho.
 */
module.exports = {
  content: [
    "../app/templates/**/*.html",
    "../app/static/js/**/*.js",
  ],
  darkMode: false,
  theme: {
    extend: {},
  },
  plugins: [],
};
