// 取报告：浏览器里直接 fetch 会被 CORS 挡（mjai.ekyu.moe 不返回 Access-Control-Allow-Origin）；
// 打包成 APK 后走 CapacitorHttp（原生请求，没有 CORS）。浏览器里调试时可以用「导入 JSON」代替。
// Mac 壳（WKWebView）里由壳代理 /report/*，是同源请求，没有 CORS；浏览器和安卓照旧走远端
const MAC = typeof window !== 'undefined' && !!window.MJ_MAC;
const SITE = MAC ? '/report/' : 'https://mjai.ekyu.moe/report/';

/** 从粘贴的文本里取 16 位报告 id：支持裸 id、killerducky 链接、任意带 id 的链接 */
export function extractRid(text) {
  const s = (text || '').trim();
  let m = /([0-9a-f]{16})/i.exec(s);
  return m ? m[1].toLowerCase() : null;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function capacitorHttp() {
  const p = window.Capacitor && window.Capacitor.Plugins;
  return p && p.CapacitorHttp ? p.CapacitorHttp : null;
}

/** 取一份报告。404 时重试 3 次、每次间隔 2 秒（和桌面版一致：刚提交的报告还没生成好）。
 *  返回 {ok:true, data} 或 {ok:false, reason:'404'|'cors'|'net'|'bad', message} */
export async function fetchReport(rid, onNote = () => {}) {
  const url = SITE + rid + '.json';
  const http = capacitorHttp();
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      let status;
      let text;
      if (http) {
        const res = await http.get({ url, responseType: 'text', headers: { Accept: 'application/json' } });
        status = res.status;
        text = typeof res.data === 'string' ? res.data : JSON.stringify(res.data);
      } else {
        const res = await fetch(url, { headers: { Accept: 'application/json' } });
        status = res.status;
        text = await res.text();
      }
      if (status === 200) {
        try {
          const data = JSON.parse(text);
          if (!data || !data.review || !data.mjai_log) return { ok: false, reason: 'bad', message: '这份 JSON 里没有 Mortal 的分析结果。' };
          return { ok: true, data };
        } catch {
          return { ok: false, reason: 'bad', message: '下载到的不是 JSON（可能是错误页）。' };
        }
      }
      if (status === 404) {
        if (attempt < 3) {
          onNote(`报告还没生成好（404），${2} 秒后重试（${attempt + 1}/3）`);
          await sleep(2000);
          continue;
        }
        return { ok: false, reason: '404', message: '报告还没生成好或已过期（404）。等网站跑完再试。' };
      }
      return { ok: false, reason: 'net', message: `服务器返回 ${status}。` };
    } catch (e) {
      const msg = String(e && e.message ? e.message : e);
      const isCors = !http && /Failed to fetch|NetworkError|Load failed/i.test(msg);
      if (isCors) {
        return {
          ok: false,
          reason: 'cors',
          message: '浏览器不让网页直接读这个网站（CORS）。可以：① 把这个地址在浏览器里打开、另存为 .json 再「导入报告」；② 打包成 APK 后走原生请求，就没这个问题。',
        };
      }
      if (attempt < 3 && /timeout|timed out/i.test(msg)) { await sleep(2000); continue; }
      return { ok: false, reason: 'net', message: msg };
    }
  }
  return { ok: false, reason: 'net', message: '重试次数用完。' };
}

/** 让用户选一个本地 .json 报告文件 */
export function pickJsonFile() {
  return new Promise((resolve) => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = '.json,application/json';
    inp.onchange = () => {
      const f = inp.files && inp.files[0];
      if (!f) { resolve(null); return; }
      const fr = new FileReader();
      fr.onload = () => {
        try { resolve({ name: f.name, data: JSON.parse(String(fr.result)) }); }
        catch { resolve({ name: f.name, error: '这个文件不是合法的 JSON。' }); }
      };
      fr.onerror = () => resolve({ name: f.name, error: '读文件失败。' });
      fr.readAsText(f, 'utf-8');
    };
    inp.click();
  });
}

/** 让用户选一个本地文件，按二进制读回来（备份 .json.gz 要走这个） */
export function pickFileBuffer(accept = '.json,.gz,application/json,application/gzip') {
  return new Promise((resolve) => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = accept;
    inp.onchange = () => {
      const f = inp.files && inp.files[0];
      if (!f) { resolve(null); return; }
      const fr = new FileReader();
      fr.onload = () => resolve({ name: f.name, buffer: fr.result });
      fr.onerror = () => resolve({ name: f.name, error: '读文件失败。' });
      fr.readAsArrayBuffer(f);
    };
    inp.click();
  });
}
