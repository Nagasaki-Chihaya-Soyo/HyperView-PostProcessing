import os
import re
import subprocess
import fnmatch
from typing import Optional
from .logging_util import log_info, log_error, log_debug


class HVProcess:
    def __init__(self, config: dict):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.shortcut_path: Optional[str] = None
        self.version: Optional[str] = None

    def find_shortcut(self) -> Optional[str]:
        if self.shortcut_path and os.path.exists(self.shortcut_path):
            return self.shortcut_path
        pattern = self.config.get('shortcut_pattern', 'HyperView*.lnk')
        search_paths = self.config.get('search_paths', [])

        user_profile = os.environ.get('USERPROFILE', '')
        if user_profile:
            search_paths.extend([
                os.path.join(user_profile, 'Desktop'),
                os.path.join(user_profile, 'AppData/Roaming/Microsoft/Windows/Start Menu/Programs'),
            ])
        search_paths.extend([
            'C:/Users/Public/Desktop',
            'C:/ProgramData/Microsoft/Windows/Start Menu/Programs',
        ])
        altair_base = 'C:/ProgramData/Microsoft/Windows/Start Menu/Programs'
        if os.path.exists(altair_base):
            try:
                for folder in os.listdir(altair_base):
                    if folder.lower().startswith('altair'):
                        altair_path = os.path.join(altair_base, folder)
                        search_paths.append(altair_path)
                        if os.path.isdir(altair_path):
                            try:
                                for sub in os.listdir(altair_path):
                                    sub_path = os.path.join(altair_path, sub)
                                    if os.path.isdir(sub_path):
                                        search_paths.append(sub_path)
                            except (PermissionError, OSError) as e:
                                log_error(f"Cannot read subdirectory {altair_path}: {e}")
            except (PermissionError, OSError) as e:
                log_error(f"Cannot read directory {altair_base}: {e}")
        for base_path in search_paths:
            if not os.path.exists(base_path):
                continue
            for root, dirs, files in os.walk(base_path):
                for f in files:
                    if fnmatch.fnmatch(f, pattern):
                        self.shortcut_path = os.path.join(root, f)
                        log_info(f"HyperView Found In :{self.shortcut_path}")
                        self.detect_version()
                        return self.shortcut_path
        log_error("NOT FOUND HYPERVIEW LINK")
        return None

    def detect_version(self) -> Optional[str]:
        """从快捷方式路径中提取 HyperView 版本号，并打印到控制台。"""
        if not self.shortcut_path:
            return None
        path = self.shortcut_path.replace('\\', '/')
        print(f"[HyperView] Shortcut path: {path}")
        # Match "2024.1" or standalone year like "2024"
        match = re.search(r'\b(20[12]\d(?:\.\d+)?)\b', path)
        if match:
            self.version = match.group(1)
            print(f"[HyperView] Detected version: {self.version}")
            log_debug(f"HyperView version detected: {self.version}")
        else:
            self.version = None
            print("[HyperView] Version: unknown (no version string found in shortcut path)")
            log_debug("HyperView version could not be detected from shortcut path")
        return self.version

    def get_version_year(self) -> int:
        """从版本字符串提取年份，如 '2024.1' -> 2024, '2024' -> 2024, None -> 0"""
        if not self.version:
            return 0
        try:
            return int(self.version.split('.')[0])
        except ValueError:
            return 0

    def ensure_shortcut_detected(self) -> bool:
        """确保快捷方式已找到且版本已检测，不启动进程。"""
        return self.find_shortcut() is not None

    def start(self, agent_path: str, mode: str = "tcl") -> bool:
        shortcut = self.find_shortcut()
        if not shortcut:
            return False
        agent_path = agent_path.replace('\\', '/')
        try:
            cmd = f'cmd /c start "" "{shortcut}" -tcl "{agent_path}"'
            log_info(f"Start Command:{cmd}")
            self.process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            log_info(f"Starting HyperView (mode={mode})...")
            return True
        except Exception as e:
            log_error(f"Failed to Starting Hyperview:{e}")
            return False

    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    def terminate(self):
        if self.process and self.is_running():
            self.process.terminate()
            log_info("Hyperview has been terminated now")
