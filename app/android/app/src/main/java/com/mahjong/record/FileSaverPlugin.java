package com.mahjong.record;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;

import androidx.activity.result.ActivityResult;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.Map;

/**
 * 保存文件 + 调试日志。
 *
 * 保存流程改成三步，避免把整个文件内容塞进一次插件调用：
 *   open(token, fileName, mime)  弹系统的「保存到…」（ACTION_CREATE_DOCUMENT），用户选完目录和文件名
 *   write(token, data)           分块写，JS 每块 32 KB
 *   close(token)                 写完关闭
 *
 * 为什么：备份 JSON 一场就有 700 KB 以上。以前把整段内容当参数一次传过来，选完文件回到应用时
 * Capacitor 要恢复这个巨大的待处理调用，容易 OOM/崩溃（表现就是文件建好了但 0 字节、应用闪退）。
 * 现在跨桥的每次只有 32 KB，而且 token 很小，系统回收后重来也不会崩。
 */
@CapacitorPlugin(name = "FileSaver")
public class FileSaverPlugin extends Plugin {

    // 插件方法可能在不同线程被调用，用并发容器
    private final Map<String, OutputStream> streams = new java.util.concurrent.ConcurrentHashMap<>();

    @PluginMethod
    public void open(PluginCall call) {
        String fileName = call.getString("fileName", "export.txt");
        String mime = call.getString("mime", "text/plain");
        if (call.getString("token") == null) {
            call.reject("缺少 token");
            return;
        }
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType(mime);
        intent.putExtra(Intent.EXTRA_TITLE, fileName);
        startActivityForResult(call, intent, "onPick");
    }

    @ActivityCallback
    private void onPick(PluginCall call, ActivityResult result) {
        if (call == null) {
            return;   // 进程被系统回收后恢复，这次就没有回调了，JS 会拿到 reject
        }
        String token = call.getString("token");
        if (token == null) {
            call.reject("缺少 token");
            return;
        }
        if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null) {
            call.reject("cancelled");
            return;
        }
        try {
            Uri uri = result.getData().getData();
            OutputStream os = getContext().getContentResolver().openOutputStream(uri, "w");
            if (os == null) {
                call.reject("打不开目标文件");
                return;
            }
            streams.put(token, os);
            JSObject ret = new JSObject();
            ret.put("token", token);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("打开失败：" + e.getMessage());
            appendLog("open 失败: " + e);
        }
    }

    @PluginMethod
    public void write(PluginCall call) {
        String token = call.getString("token");
        String data = call.getString("data", "");
        boolean base64 = Boolean.TRUE.equals(call.getBoolean("base64", false));
        OutputStream os = streams.get(token);
        if (os == null) {
            call.reject("写入会话已失效（可能被系统回收），请重新导出");
            return;
        }
        try {
            byte[] bytes = base64
                    ? android.util.Base64.decode(data, android.util.Base64.DEFAULT)
                    : data.getBytes(StandardCharsets.UTF_8);
            os.write(bytes);
            JSObject ret = new JSObject();
            ret.put("bytes", bytes.length);
            call.resolve(ret);
        } catch (Exception e) {
            // 写失败就把句柄关掉并清出表，否则这个 token 对应的流永远泄漏
            closeQuietly(streams.remove(token));
            call.reject("写入失败：" + e.getMessage());
            appendLog("write 失败: " + e);
        }
    }

    private void closeQuietly(OutputStream os) {
        if (os == null) return;
        try {
            os.close();
        } catch (Exception ignored) {
            // 已经出错了，关闭再失败也没别的办法
        }
    }

    @PluginMethod
    public void close(PluginCall call) {
        String token = call.getString("token");
        OutputStream os = streams.remove(token);
        if (os == null) {
            call.resolve();
            return;
        }
        try {
            os.flush();
            os.close();
            call.resolve();
        } catch (Exception e) {
            call.reject("关闭失败：" + e.getMessage());
            appendLog("close 失败: " + e);
        }
    }

    // ---------------------------------------------------------------- 日志
    private File logFile() {
        return new File(getContext().getFilesDir(), "debug.log");
    }

    private synchronized void appendLog(String line) {
        try {
            // 日志超过 1 MB 就先清空，避免无限追加把存储写满
            File f = logFile();
            if (f.length() > 1024 * 1024) new FileOutputStream(f, false).close();
        } catch (Exception ignored) {
            // 清空失败就算了
        }
        try (FileOutputStream fos = new FileOutputStream(logFile(), true)) {
            String ts = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date());
            fos.write((ts + " [native] " + line + "\n").getBytes(StandardCharsets.UTF_8));
        } catch (Exception ignored) {
            // 日志写不进去不能影响主流程
        }
    }

    @PluginMethod
    public void log(PluginCall call) {
        String line = call.getString("line", "");
        appendLog(line);
        call.resolve();
    }

    @PluginMethod
    public void readLog(PluginCall call) {
        String text = "";
        String path = logFile().getAbsolutePath();
        try (InputStream in = new java.io.FileInputStream(logFile())) {
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                bos.write(buf, 0, n);
                if (bos.size() > 512 * 1024) {
                    bos.write("\n…（日志超过 512 KB，已截断）\n".getBytes(StandardCharsets.UTF_8));
                    break;
                }
            }
            text = bos.toString("UTF-8");
        } catch (Exception ignored) {
            text = "";
        }
        JSObject ret = new JSObject();
        ret.put("log", text);
        ret.put("path", path);
        call.resolve(ret);
    }

    @PluginMethod
    public void clearLog(PluginCall call) {
        //noinspection ResultOfMethodCallIgnored
        logFile().delete();
        call.resolve();
    }
}
