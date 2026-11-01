/**
 * Generates a GoFile Website Token by fetching and eval'ing wt.obf.js.
 * The server-side secret rotates but the function name `generateWT` is stable.
 *
 * Usage: node gofile_wt.mjs <accountToken>
 */
import vm from "node:vm";
import https from "node:https";

const token = process.argv[2];
if (!token) {
  console.error("Usage: node gofile_wt.mjs <accountToken>");
  process.exit(1);
}

const UA =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const code = await new Promise((resolve, reject) => {
  https
    .get("https://gofile.io/js/wt.obf.js", (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => resolve(data));
    })
    .on("error", reject);
});

const ctx = {
  navigator: { userAgent: UA, language: "en-US" },
  performance: { timeOrigin: Date.now() },
  console,
};
vm.createContext(ctx);
vm.runInContext(code, ctx);
if (typeof ctx.generateWT !== "function") {
  console.error("generateWT not found. keys:", Object.keys(ctx));
  process.exit(1);
}
process.stdout.write(ctx.generateWT(token));
