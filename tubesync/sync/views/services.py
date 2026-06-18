import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass(frozen=True)
class ServiceStatus:
    """Strongly typed representation of an s6 service state."""
    name: str
    is_running: bool
    is_wanted_up: bool
    is_normally_up: bool
    is_ready: bool
    pid: Optional[int]
    pgid: Optional[int]
    exit_code: Optional[int]
    signal_name: Optional[str]
    elapsed_seconds: int


class S6OverlayReporter:
    """Queries and reports on available and user-bundled s6 services."""

    SERVICE_DIR = Path('/run/service')
    S6_BIN_DIR = Path('/command')

    def __init__(self, bundle_name: str = 'user'):
        self.bundle_name = bundle_name

    def _get_bundle_services(self) -> Set[str]:
        """Resolves the exact set of service names inside the target s6-rc bundle."""
        try:
            binary = str(self.S6_BIN_DIR / 's6-rc')
            cmd = [binary, '-e', 'list', self.bundle_name]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return set()
        else:
            return set(result.stdout.strip().split())

    def list_services(self, *, all_services: bool = False) -> List[str]:
        """Finds active supervised directories, optionally filtering by the bundle."""
        services = []

        if not self.SERVICE_DIR.exists():
            return services

        bundle_services = set() if all_services else self._get_bundle_services()

        for entry in self.SERVICE_DIR.iterdir():
            if entry.is_dir() and (entry / 'supervise').exists():
                if all_services or (entry.name in bundle_services):
                    services.append(entry.name)

        return sorted(services)

    def get_service_status(self, service_name: str) -> Optional[ServiceStatus]:
        """Queries programmatic fields directly from s6-svstat."""
        service_path = self.SERVICE_DIR / service_name
        if not service_path.exists():
            return None

        fields = [
            'up', 'wantedup', 'normallyup', 'ready',
            'pid', 'pgid', 'exitcode', 'signal', 'updownfor',
        ]

        try:
            binary = str(self.S6_BIN_DIR / 's6-svstat')
            cmd = [binary, '-o', ','.join(fields), str(service_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        else:
            return self._parse_tokens(service_name, result.stdout.strip().split())

    def _parse_tokens(self, name: str, tokens: List[str]) -> ServiceStatus:
        """Transforms ordered string outputs from s6-svstat -o into explicit types."""
        is_running = ('true' == tokens.__getitem__(0))
        is_wanted_up = ('true' == tokens.__getitem__(1))
        is_normally_up = ('true' == tokens.__getitem__(2))
        is_ready = ('true' == tokens.__getitem__(3))

        raw_pid = int(tokens.__getitem__(4))
        raw_pgid = int(tokens.__getitem__(5))
        raw_exit = int(tokens.__getitem__(6))
        raw_signal = tokens.__getitem__(7)
        elapsed_seconds = int(tokens.__getitem__(8))

        pid = None if (-1 == raw_pid) else raw_pid
        pgid = None if (-1 == raw_pgid) else raw_pgid

        exit_code = None if (is_running or -1 == raw_exit) else raw_exit
        signal_name = None if (is_running or 'NA' == raw_signal) else raw_signal

        return ServiceStatus(
            name=name,
            is_running=is_running,
            is_wanted_up=is_wanted_up,
            is_normally_up=is_normally_up,
            is_ready=is_ready,
            pid=pid,
            pgid=pgid,
            exit_code=exit_code,
            signal_name=signal_name,
            elapsed_seconds=elapsed_seconds,
        )

    def get_report(self, *, all_services: bool = False) -> Dict[str, ServiceStatus]:
        """Gathers a system status map of the target supervised services."""
        report = {}
        for name in self.list_services(all_services=all_services):
            status = self.get_service_status(name)
            if status:
                report[name] = status
        return report


if '__main__' == __name__:
    reporter = S6OverlayReporter(bundle_name='user')
    print(f'Polled directory: {reporter.SERVICE_DIR}\n')

    services_report = reporter.get_report(all_services=False)

    print(f'{"SERVICE":<25} {"STATE":<10} {"PID":<8} {"TIME ELAPSED":<15} {"READY"}')
    print('-' * 70)
    for svc_name, info in services_report.items():
        state = '🟢 UP' if info.is_running else '🔴 DOWN'
        pid_str = str(info.pid) if info.pid else '-'
        ready_str = '✓' if info.is_ready else '-'
        time_str = f'{info.elapsed_seconds}s'

        print(f'{svc_name:<25} {state:<10} {pid_str:<8} {time_str:<15} {ready_str}')
