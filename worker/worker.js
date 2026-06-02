// 小説共有サイト用・短縮リンクストア（Cloudflare Workers + KV）
//
// POST /            本文（base64urlのペイロード）を保存し {key} を返す
// GET  /<key>       保存した本文を返す
// OPTIONS           CORS プリフライト
//
// KV バインディング名: NOVELS

const MAX_BYTES = 1_500_000;            // 1.5MB 上限（巨大投稿・荒らし対策）
const TTL_SECONDS = 60 * 60 * 24 * 365; // 1年で自動失効
// 紛らわしい文字(0,O,1,l,I)を除いた英数字
const ALPHA = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";

function makeKey(n) {
  const buf = crypto.getRandomValues(new Uint8Array(n));
  let s = "";
  for (let i = 0; i < n; i++) s += ALPHA[buf[i] % ALPHA.length];
  return s;
}

function cors(extra) {
  return Object.assign(
    {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
    },
    extra || {}
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors() });
    }

    if (request.method === "POST") {
      const body = await request.text();
      const size = new TextEncoder().encode(body).length;
      if (!body || size === 0) {
        return new Response("empty", { status: 400, headers: cors() });
      }
      if (size > MAX_BYTES) {
        return new Response("too large", { status: 413, headers: cors() });
      }
      // 衝突しないキーを生成
      let key = "";
      for (let i = 0; i < 6; i++) {
        key = makeKey(8);
        if ((await env.NOVELS.get(key)) === null) break;
      }
      await env.NOVELS.put(key, body, { expirationTtl: TTL_SECONDS });
      return new Response(JSON.stringify({ key }), {
        headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (request.method === "GET") {
      const key = url.pathname.replace(/^\/+/, "").split("/")[0];
      if (!key) {
        return new Response("novel-share OK", { headers: cors() });
      }
      const value = await env.NOVELS.get(key);
      if (value === null) {
        return new Response("not found", { status: 404, headers: cors() });
      }
      return new Response(value, {
        headers: cors({ "Content-Type": "text/plain; charset=utf-8" }),
      });
    }

    return new Response("method not allowed", { status: 405, headers: cors() });
  },
};
