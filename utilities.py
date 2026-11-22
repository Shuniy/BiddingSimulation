import csv
import signal
from collections.abc import Iterable
from os import PathLike
from pathlib import Path


def export_to_csv(output_csv_file: str | PathLike[str], data_list: Iterable[object]) -> None:
    """Append one semicolon-delimited row, creating parent directories as needed."""
    path = Path(output_csv_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as output:
        csv.writer(output, delimiter=";").writerow(data_list)


# Timeout class used to stop bots if they take too long to bid
class timeout:
    def __init__(self, seconds=1, error_message="Timeout"):
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        signal.alarm(0)
