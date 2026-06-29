__maker__ = "SmokerGreenOG"
import _protect

import re

URL_RE = re.compile(rb"https?://[^\s'\"<>()\[\]{}]+", re.I)
IP_RE = re.compile(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b")
EMAIL_RE = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PACKAGE_RE = re.compile(rb"\b[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*){2,}\b")

SECRET_PATTERNS = {
    "google_api_key": re.compile(rb"AIza[0-9A-Za-z_\-]{20,}"),
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "generic_token": re.compile(
        rb"(?i)(?:api[_-]?key|secret|token|bearer|client[_-]?secret)"
        rb"[\"'\s:=]{1,8}[A-Za-z0-9_\-.]{16,}"
    ),
    "jwt": re.compile(rb"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
    "private_key_marker": re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
}

SUSPICIOUS_PERMISSIONS = {
    "android.permission.READ_SMS",
    "android.permission.SEND_SMS",
    "android.permission.RECEIVE_SMS",
    "android.permission.READ_CONTACTS",
    "android.permission.WRITE_CONTACTS",
    "android.permission.RECORD_AUDIO",
    "android.permission.CAMERA",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.READ_CALL_LOG",
    "android.permission.WRITE_CALL_LOG",
    "android.permission.SYSTEM_ALERT_WINDOW",
    "android.permission.REQUEST_INSTALL_PACKAGES",
    "android.permission.BIND_ACCESSIBILITY_SERVICE",
    "android.permission.QUERY_ALL_PACKAGES",
}

RISKY_STRINGS = [
    b"DexClassLoader",
    b"PathClassLoader",
    b"Runtime.getRuntime",
    b"ProcessBuilder",
    b"/system/bin/sh",
    b"/system/xbin/su",
    b"getDeviceId",
    b"READ_SMS",
    b"SEND_SMS",
    b"AccessibilityService",
    b"REQUEST_INSTALL_PACKAGES",
    b"WebView.addJavascriptInterface",
]
