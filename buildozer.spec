[app]
# 应用名称
title = T0Trading
# 包名
package.name = t0trading
# 包域名
package.domain = com.trading
# 源代码目录
source.dir = .
# 主文件
source.include_exts = py,png,jpg,kv,atlas,json
# 应用版本
version = 1.0.0
# 应用图标 (需要准备icon.png)
# icon.filename = icon.png
# 启动画面 (需要准备presplash.png)
# presplash.filename = presplash.png

# 需要的权限
android.permissions = INTERNET,ACCESS_NETWORK_STATE,VIBRATE,RECEIVE_BOOT_COMPLETED

# Python版本
python_for_android.python = 3.9

# 架构
android.archs = arm64-v8a,armeabi-v7a

# API级别
android.api = 31
android.minapi = 21
android.ndk_api = 21

# SDK和NDK路径 (如果需要指定)
# android.sdk_path = 
# android.ndk_path = 

# 依赖
requirements = python3,kivy,requests,numpy

# 入口点
entrypoint = main.py

# 日志级别
log_level = 2

# 方向 (portrait=竖屏, landscape=横屏, all=自动)
orientation = portrait

# 全屏
fullscreen = 0

# 预加载
android.accept_sdk_license = True

[buildozer]
# 日志级别
log_level = 2
# 警告模式
warn_on_root = 1
