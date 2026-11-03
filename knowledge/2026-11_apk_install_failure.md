# Android 发行包体积与下载失败排查（2026-11）

## 现象

App 发版后，两台测试机安装失败，提示 **`packageinfo is null`**；但部分用户更新成功。

## 结论先行

`packageinfo is null` ≠ 包损坏、≠ 签名问题。**包在传输途中被截断了。**

- 服务器上的文件是完整的（`md5sum` 与本地构建一致，`unzip -l` 能列出 960 个条目）
- 完整下载后用 `adb install` 一次成功
- 所以问题只在**下载环节**

## 怎么定位的

### 1. 先比大小和 MD5

```bash
# 服务器
ssh j 'md5sum ~/www/download/music/app/yinhe-music.apk; stat -c %s ...'
# 本地下载
curl -sL -o dl.apk -w "%{http_code} %{size_download}\n" https://jvkit.cn/download/music/app/yinhe-music.apk
md5sum dl.apk
```

第一次 curl 只拿到 10,895,089 字节（应为 28,792,380），**MD5 自然对不上**。

### 2. 看 nginx access.log（决定性证据）

```bash
sudo grep "yinhe-music.apk" /var/log/nginx/access.log | tail -12
```

```
206 7290570   ← 7.2MB 断
206 7811914   ← 7.8MB 断
206 9597460   ← 9.5MB 断
206 9731786   ← 9.7MB 断
200 9682673   ← 9.6MB 断
```

**每次都在 7~11MB 处断掉，反复重试都过不去。** `206` 说明手机浏览器在自动续传，但单次连接撑不到 28MB。

### 3. 排除服务器侧问题

- `uptime` load 0.05、`free -m` 空闲 2GB → 不是负载问题
- `curl -H "Range: bytes=..."` 返回 206 且分块字节数精确 → Range 支持正常
- 三块分别下载后 `cat` 合并，MD5 与服务器一致 → 文件本身没坏

结论：**链路慢且会间歇性中断**。本次实测 28MB 走 **79.7 秒、361 KB/s**。

## 根因

APK 是 **debug 包，28MB**，其中 `classes*.dex` 未压缩合计 36MB（`classes.dex` 17.5MB、`classes13.dex` 10.5MB、`classes14.dex` 7.8MB）。

原因：`app/build.gradle.kts` 里**从来没配 `buildTypes`**，一直没有 release 构建，发的一直是 debug 包。

慢链路下 80 秒的下载，中途断一次就得重来（手机浏览器多数不支持断点续传），于是拿到残缺包 → `packageinfo is null`。

## 修复

### 1. 加 release 构建（体积减半以上）

```kotlin
buildTypes {
    release {
        isMinifyEnabled = true
        isShrinkResources = true
        signingConfig = signingConfigs.getByName("debug")   // 关键
        proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
}
```

**签名必须沿用 debug key**：已经发出去的包是 debug 签名的，换 key 会导致老用户无法覆盖安装（报「应用未安装」或签名冲突）。所以只做代码压缩，不换签名。

ProGuard 必须 keep 的部分（这些靠反射，压了会运行时崩）：
- Gson 的数据类：`data.remote.**`、`data.local.**`
- `com.google.gson.reflect.TypeToken` 及其子类
- Retrofit 的 `Call`/`Response`/`Continuation`
- Room 的 `* extends RoomDatabase`
- Manifest 里声明的 Service：`SystemCaptureService`、`BubbleService`、`YinHeMediaService`

### 2. 发布 MD5 供校验

```bash
md5sum ~/www/download/music/app/yinhe-music.apk | cut -d" " -f1 > ~/www/download/music/app/yinhe-music.apk.md5
```

## 可复用的排查口诀

| 现象 | 先查什么 |
|---|---|
| `packageinfo is null` / 解析失败 | **下载是否完整**：比 `size` 和 `md5`，别看它"像个 apk" |
| 安装报「应用未安装」 | 签名不一致（用了新 key）或降级安装 |
| 老用户无法覆盖安装 | 签名变了，或 versionCode 没加 |
| 下载总在固定大小断 | 看 nginx access.log 的 `206` 次数和字节数 |

## 其他记录

- 国内链路到这台服务器（82.157.178.112）实测 360 KB/s 左右，28MB 要 80 秒，**大包在这个链路上不可靠**
- `scp` 在这台 Windows 上是坏的（会被当成 `cp` 执行），上传一律走 `cat 文件 | ssh j 'cat > 路径'` 或 sftp
- 本机 OpenSSH 出现过 `socket: No buffer space available` 导致完全连不上（端口可达、ping 通），
  可用 Python `paramiko` 临时替代：
  ```python
  import paramiko
  c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
  c.connect('82.157.178.112', username='ubuntu', key_filename=r'C:/Users/junvon/.ssh/place', timeout=20)
  ```
  注意这是临时手段，不是项目依赖。
