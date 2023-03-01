__version_info__ = (1, 0, 4)
__version__ = ".".join(map(str, __version_info__))
__author__ = (
    "Jan Eberhage, Institute for Biophysical Chemistry, "
    "Hannover Medical School (eberhage.jan@mh-hannover.de)"
)

import os
import sys
import argparse
import yaml
import json
import logging
import time
import datetime
from pathlib import Path
import subprocess
import importlib.util


class CustomFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    # format = '%(asctime)s [%(levelname)-7s] %(message)s'
    format = "%(asctime)s :: %(message)s"
    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, "%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


class AlphaFoldJob:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.alphafold_path = Path(self.alphafold_path)
        self.data_dir = Path(self.data_dir)
        self.output_dir = Path(self.output_dir)
        self.job_dir = self.output_dir / self.name
        self.fasta_paths = self.job_dir / f"{self.name}.fasta"
        log.info("Creating the following job:")
        for key, val in self.__dict__.items():
            log.info(f"{key.ljust(35)}: {val}")

    def generate_fasta(self):
        self.job_dir.mkdir(parents=True, exist_ok=True)
        with open(self.fasta_paths, "w") as f:
            [
                f.write(f">{key}\n{val}\n")
                for key, val
                in self.sequences.items()
            ]

    def run_alphafold(self):
        subprocess_list = ["python3"]
        subprocess_list.append(
            self.alphafold_path / "alphafold-main" / "docker" / "run_docker.py"
        )

        for param in [
            "max_template_date",
            "data_dir",
            "docker_user",
            "output_dir",
            "fasta_paths",
        ]:
            subprocess_list.append(f"--{param}={getattr(self, param)}")

        for optional_param in [
            "model_preset",
            "num_multimer_predictions_per_model",
            "models_to_relax",
        ]:
            if hasattr(self, optional_param):
                subprocess_list.append(
                    f"--{optional_param}={getattr(self, optional_param)}"
                )

        af_process = subprocess.run(subprocess_list)
        return af_process.returncode

    def print_job_details(self):
        with open(self.job_dir / "alphabuddy_job_details.json", "w") as f:
            json.dump(self.__dict__, f, indent=2)

    def run_alphaplots(self, settings):
        if not hasattr(self, "alphaplots"):
            pass
        alphaplots_path = Path(settings["alphaplots"]["path"])
        subprocess_list = [
            "python3",
            alphaplots_path,
            f"--input_dir={self.job_dir}",
            "--yes",
        ]

        for param in ["rmpkl", "jsondump"]:
            if param in self.alphaplots:
                subprocess_list.append(f"--{param}")

        subprocess.run(subprocess_list)


def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)
    return logger


def check_settings(settings):
    if (
        "versions" not in settings or
        not isinstance(settings["versions"], dict)
    ):
        log.error(
            "The settings file seems to have a bad layout for the »versions«. "
            "It should be a dictionary. Exiting."
        )
        sys.exit(1)

    default_version = next(
        (
            version
            for version, version_params in settings["versions"].items()
            if version_params.get("default") is True
        ),
        None,
    )

    if not default_version:
        log.error(
            "No default version was chosen under »versions«/<version> in the "
            "settings. Exiting."
        )
        sys.exit(1)
    if not settings["versions"][default_version].get("data_dir"):
        log.error(
            "A »data_dir« has to be provided under »versions«/<version> in "
            "the settings. Exiting."
        )
        sys.exit(1)
    if not settings["versions"][default_version].get("path"):
        log.error(
            "A »path« has to be provided under »versions«/<version> in the "
            "settings. Exiting."
        )
        sys.exit(1)

    if settings.get("alphaplots"):
        try:
            module_spec = importlib.util.find_spec("matplotlib")
            if module_spec is None:
                log.error("Module »matplotlib« is not installed.")
                log.error("Please try »python3 -m pip install matplotlib«.")
                sys.exit(1)
        except ImportError:
            log.error("Module »matplotlib« is not installed.")
            log.error("Please try »python3 -m pip install matplotlib«.")
            sys.exit(1)
        if not settings["alphaplots"].get("path") or not os.path.exists(
            settings["alphaplots"]["path"]
        ):
            log.error(
                "»alphaplots« was not found under the path given in the "
                "settings. Aborting."
            )
            sys.exit(1)

    log.info("Found valid settings")


def get_next_job(path):
    jobs = [
        entry
        for entry in os.scandir(path)
        if entry.is_file() and entry.name.endswith((".yaml", ".yml"))
    ]

    if not jobs:
        return False
    jobs.sort(key=lambda x: os.path.getmtime(x))
    for job in jobs:
        job_dict = yaml.safe_load(open(job.path))
        if "urgent" in job_dict and job_dict["urgent"] is True:
            return job
    return jobs[0]


def check_config(job, settings):
    try:
        with open(job.path, "r") as f:
            job_dict = yaml.safe_load(f)
    except Exception:
        log.warning(f"The file »{job.path}« could not be loaded. Skipping.")
        return False

    if (
        "version" in job_dict and
        job_dict["version"] not in settings["versions"]
    ):
        log.warning(
            f"The file »{job.path}« contains a value for the key »version« "
            "that is not included in your settings file. Skipping."
        )
        return False

    if "sequences" not in job_dict:
        log.warning(
            f"The file »{job.path}« has no »sequences«. This is mandatory. "
            "Skipping."
        )
        return False

    sequences = job_dict["sequences"]
    if not isinstance(sequences, dict) or not sequences:
        log.warning(
            f"The file »{job.path}« seems to have a bad layout for the "
            "»sequences«. It should be an indented dictionary. Skipping."
        )
        return False

    return True


def create_alphafold_job(job, settings, args):
    job_dict = yaml.safe_load(open(job.path))

    job_dict.setdefault(
        "version",
        next(
            i
            for i, version in settings["versions"].items()
            if version.get("default")
        ),
    )
    job_dict.setdefault("name", Path(job.path).stem)
    job_dict.setdefault(
        "max_template_date", datetime.datetime.today().strftime("%Y-%m-%d")
    )
    job_dict.setdefault(
        "output_dir",
        settings.get("output_dir", os.path.join(args.directory, "results")),
    )

    job_dict["data_dir"] = settings["versions"][job_dict["version"]].get(
        "data_dir"
    )
    job_dict["alphafold_path"] = settings["versions"][job_dict["version"]].get(
        "path"
    )
    job_dict["docker_user"] = settings.get("docker_user", "root")

    return AlphaFoldJob(**job_dict)


def move_job(job, directory, target_dir_name):
    target_dir_path = os.path.join(directory, target_dir_name)
    if not os.path.exists(target_dir_path):
        os.mkdir(target_dir_path)
    os.rename(job.path, os.path.join(target_dir_path, job.name))
    log.info(f"Moving job to »{target_dir_path}«.")


def main():
    global log
    log = setup_logging()

    parser = argparse.ArgumentParser(
        add_help=False,
        description=(
            "This script will run AlphaFold with the given sequences "
            "and configurations provided in the directory."
            )
    )
    parser.add_argument(
        "directory",
        metavar="<alphabuddy_dir>",
        help="Relative or absolute path to the alphabuddy directory"
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="%(prog)s (" + __version__ + ") " + " by " + __author__
    )
    parser.add_argument(
        "-h", "--help", action="help", help="show this help message and exit"
    )
    args = parser.parse_args()

    input_path = os.path.join(args.directory, "input")
    if not os.path.exists(input_path):
        log.error(f"»{os.path.abspath(input_path)}« was not found. Aborting.")
        sys.exit(1)

    while True:
        settings_path = os.path.join(args.directory, "settings.yaml")
        if not os.path.exists(settings_path):
            log.error(
                f"The file »{settings_path}« is mandatory. Please provide the "
                "settings at this specific location."
            )
            sys.exit(1)

        settings = yaml.safe_load(open(settings_path))
        check_settings(settings)

        next_job = get_next_job(input_path)

        if next_job:
            if check_config(next_job, settings):
                job = create_alphafold_job(next_job, settings, args)
                job.generate_fasta()
                code = job.run_alphafold()
                if code:
                    move_job(next_job, args.directory, "failed_jobs")
                else:
                    move_job(next_job, args.directory, "done_jobs")
                    job.run_alphaplots(settings)
                    job.print_job_details()
            else:
                move_job(next_job, args.directory, "failed_jobs")
        else:
            log.info("Waiting for jobs. CTRL+C for interuption.")
            while not [
                entry
                for entry in os.scandir(input_path)
                if entry.is_file() and entry.name.endswith((".yaml", ".yml"))
            ]:
                time.sleep(3)


if __name__ == "__main__":
    main()
