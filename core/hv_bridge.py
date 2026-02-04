import os
import json
import time
import uuid
import shutil
from typing import Optional, Dict
from .logging_util import log_info, log_error, log_debug


class HVBridge:
    def __init__(self, inbox_dir: str, outbox_dir: str, timeout: float = 300):
        self.inbox_dir = inbox_dir
        self.outbox_dir = outbox_dir
        self.timeout = timeout
        os.makedirs(inbox_dir, exist_ok=True)
        os.makedirs(outbox_dir, exist_ok=True)

    def _generate_job_id(self) -> str:
        return f"{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"

    def _write_job(self, job_id: str, job_data: Dict) -> str:
        job_file = os.path.join(self.inbox_dir, f"job_{job_id}.json")
        tmp_file = job_file + ".tmp"
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp_file, job_file)
        log_debug(f"写入任务:{job_file}")
        return job_file

    def _wait_result(self, job_id: str) -> Optional[Dict]:
        result_file = os.path.join(self.outbox_dir, f"job_{job_id}.result.json")
        error_file = os.path.join(self.outbox_dir, f"job_{job_id}.error.json")

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if os.path.exists(result_file):
                time.sleep(0.1)
                with open(result_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                log_info(f"收到结果:job_{job_id}")
                return result
            if os.path.exists(error_file):
                time.sleep(0.1)
                with open(error_file, 'r', encoding='utf-8') as f:
                    error = json.load(f)
                log_error(f"任务失败:{error.get('error', 'Unknown error')}")
                return {'success': False, 'error': error.get('error', 'Unknown error')}

            time.sleep(0.2)
        log_error(f"任务超时：job_{job_id}")
        return {'success': False, 'error': 'Timeout'}

    def send_job(self, cmd: str, params: Dict = None) -> Dict:
        job_id = self._generate_job_id()
        job_data = {
            'id': job_id,
            'cmd': cmd,
            'timestamp': time.time()
        }
        if params:
            job_data.update(params)
        log_info(f"发送任务:{cmd} (job_{job_id})")
        self._write_job(job_id, job_data)
        log_info(f"等待结果:job_{job_id}")
        result = self._wait_result(job_id)
        log_debug(f"收到原始结果: {result}")
        return result if result else {'success': False, 'error': 'No response'}

    def clear_inbox(self):
        for f in os.listdir(self.inbox_dir):
            if f.endswith('.json'):
                os.remove(os.path.join(self.inbox_dir, f))

    def clear_outbox(self):
        for f in os.listdir(self.outbox_dir):
            if f.endswith('.json'):
                os.remove(os.path.join(self.outbox_dir, f))


class ReadySignal:
    def __init__(self, ready_file: str):
        self.ready_file = ready_file

    def clear(self):
        if os.path.exists(self.ready_file):
            try:
                os.remove(self.ready_file)
            except PermissionError:
                pass

    def wait(self, timeout: float = 120, interval: float = 0.5) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.exists(self.ready_file):
                log_info("Hyperview Agent Ready")
                return True
            time.sleep(interval)
        log_error("等待 HyperView Agent OverTime")
        return False

    def is_ready(self) -> bool:
        return os.path.exists(self.ready_file)
