__version_info__ = (1, 1, 0)
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


class Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (Path, datetime.date, datetime.timedelta)):
            return str(obj)
        return super().default(obj)


class AlphaFoldJob:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.start_time = datetime.datetime.now()
        self.alphafold_path = Path(self.alphafold_path).resolve()
        self.alphafold_venv = Path(self.alphafold_venv).resolve()
        self.data_dir = Path(self.data_dir).resolve()
        self.output_dir = Path(self.output_dir).resolve()
        self.job_dir = self.output_dir / self.name
        self.fasta_paths = self.job_dir / f"{self.name}.fasta"
        log.info("Creating the following job:")
        for key, val in self.__dict__.items():
            log.info(f"{key.ljust(35)}: {val}")

    def generate_fasta(self):
        self.job_dir.mkdir(parents=True, exist_ok=True)
        with open(self.fasta_paths, "w") as f:
            [
                f.write(f">{name}\n{sequence}\n")
                for entry in self.sequences
                for name, sequence in entry.items()
            ]

    def run_alphafold(self):
        subprocess_list = [
            self.alphafold_venv / "bin" / "python3",
            self.alphafold_path / "docker" / "run_docker.py"
            ]

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
            "docker_image_name",
        ]:
            if hasattr(self, optional_param):
                subprocess_list.append(
                    f"--{optional_param}={getattr(self, optional_param)}"
                )

        log_file = self.job_dir / "alphafold.log"
        log.info(f"Logging AlphaFold output to ??{log_file}??.")
        af_process = subprocess_log(subprocess_list, log_file)
        return af_process.returncode

    def print_job_details(self):
        with open(self.job_dir / "alphabuddy_job_details.json", "w") as f:
            json.dump(self.__dict__, f, indent=2, cls=Encoder)

    def run_alphaplots(self, settings):
        if not hasattr(self, "alphaplots"):
            return
        alphaplots_path = Path(settings["alphaplots"].get("path"))
        alphaplots_venv = settings["alphaplots"].get("venv")

        if alphaplots_venv:
            interpreter = Path(alphaplots_venv) / "bin" / "python3"
        else:
            interpreter = "python3"

        subprocess_list = [
            interpreter,
            alphaplots_path,
            f"--input_dir={self.job_dir}",
            "--yes",
        ]

        for param in ["rmpkl", "jsondump"]:
            if param in self.alphaplots:
                subprocess_list.append(f"--{param}")

        log_file = self.job_dir / "alphaplots.log"
        log.info(f"Logging AlphaPlots output to ??{log_file}??.")
        subprocess_log(subprocess_list, log_file)


def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)
    return logger


def subprocess_log(commands, log_path):
    with open(log_path, "w") as f, subprocess.Popen(
        commands,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True
    ) as process:
        for line in process.stdout:
            sys.stdout.write(line)
            f.write(line)
            f.flush()
    return process


def check_settings(settings):
    if (
        "versions" not in settings or
        not isinstance(settings["versions"], dict)
    ):
        log.error(
            "The settings file seems to have a bad layout for the ??versions??. "
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
            "No default version was chosen under ??settings.yaml/versions??. "
            "Exiting."
        )
        sys.exit(1)

    for version, details in settings["versions"].items():
        for item in ["data_dir", "path", "venv"]:
            if not details.get(item):
                log.error(
                    f"A ??{item}?? has to be provided under ??settings.yaml/"
                    "versions/{version}??. Exiting."
                )
                sys.exit(1)
            if not Path(details.get(item)).is_dir():
                log.error(
                    f"The ??{item}?? under ??settings.yaml/versions/{version}?? "
                    "is no valid directory. Exiting."
                )
                sys.exit(1)


def check_alphaplots_requirements(settings):
    path = settings["alphaplots"].get("path")
    venv = settings["alphaplots"].get("venv")

    if not path or not Path(path).is_file():
        log.error(
            "??alphaplots?? was not found under the path given in the settings. "
            "Aborting."
            )
        sys.exit(1)

    if not venv:
        log.debug(
            "No virtual environment provided for ??alphaplots??. Fallback to "
            "standard python interpreter."
            )
        interpreter = "python3"
    else:
        interpreter = Path(venv) / "bin" / "python3"
        if not interpreter.is_file():
            log.error(
                "No python installation found in the virtual environment "
                "provided under ??settings.yaml/alphaplots/venv??. Aborting"
                )
            sys.exit(1)

    alphaplots_path = Path(path)
    subprocess_list = [
        interpreter,
        alphaplots_path,
        "--version"
    ]

    ap_check = subprocess.run(subprocess_list, stdout=subprocess.DEVNULL)

    return ap_check.returncode


def yaml_from_input(input_path):
    return list(input_path.glob("*.yaml")) + list(input_path.glob("*.yml"))


def get_next_job(input_path):
    jobs = yaml_from_input(input_path)
    if not jobs:
        return False
    jobs.sort(key=lambda x: os.path.getmtime(x))
    for job in jobs:
        try:
            with open(job, "r") as f:
                job_dict = yaml.safe_load(f)
        except Exception:
            log.warning(
                f"The file ??{job}?? could not be loaded. Skipping."
            )
            move_job(job, "failed_jobs")
            return False
        if "urgent" in job_dict and job_dict["urgent"] is True:
            return job
    return jobs[0]


def check_config(job, settings):
    try:
        with open(job, "r") as f:
            job_dict = yaml.safe_load(f)
    except Exception:
        log.warning(f"The file ??{job}?? could not be loaded. Skipping.")
        return False

    if (
        "version" in job_dict and
        job_dict["version"] not in settings["versions"]
    ):
        log.warning(
            f"The file ??{job}?? contains a value for the key ??version?? "
            "that is not included in your settings file. Skipping."
        )
        return False

    if "sequences" not in job_dict:
        log.warning(
            f"The file ??{job}?? has no ??sequences??. This is mandatory. "
            "Skipping."
        )
        return False

    sequences = job_dict["sequences"]
    if not isinstance(sequences, list) or not sequences:
        log.warning(
            f"The file ??{job}?? seems to have a bad layout for the "
            "??sequences??. It should be a list. Skipping."
        )
        return False

    return True


def create_alphafold_job(job, settings, args):
    job_dict = yaml.safe_load(open(job))

    job_dict.setdefault(
        "version",
        next(
            i
            for i, version in settings["versions"].items()
            if version.get("default")
        ),
    )
    job_dict.setdefault("name", job.stem)
    job_dict.setdefault(
        "max_template_date", datetime.datetime.today().strftime("%Y-%m-%d")
    )
    job_dict.setdefault(
        "output_dir",
        settings.get("output_dir", args.directory / "results"),
    )
    version_dict = settings["versions"][job_dict["version"]]
    job_dict["data_dir"] = version_dict.get("data_dir")
    job_dict["alphafold_path"] = version_dict.get("path")
    job_dict["alphafold_venv"] = version_dict.get("venv")
    job_dict["docker_user"] = settings.get("docker_user", "root")

    image = version_dict.get("docker_image_name")
    if image:
        job_dict["docker_image_name"] = image

    return AlphaFoldJob(**job_dict)


def move_job(job, target_dir_name):
    target_dir_path = job.parents[1] / target_dir_name
    target_dir_path.mkdir(exist_ok=True)
    job.rename(target_dir_path / job.name)
    log.info(f"Moving job to ??{target_dir_path}??.")


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
        type=Path,
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

    # Change the current working directory to resolve relative paths
    os.chdir(args.directory)

    input_path = args.directory / "input"
    settings_path = args.directory / "settings.yaml"
    if not input_path.is_dir():
        input_path.mkdir()
        log.info(
            f"??{input_path}?? was not found. The directory was created. You "
            "can put your jobs there."
            )

    if not settings_path.is_file():
        log.error(
            f"The file ??{settings_path}?? is mandatory. Please provide the "
            "settings at this specific location."
            )
        sys.exit(1)

    try:
        with open(settings_path, "r") as f:
            settings = yaml.safe_load(f)
    except Exception:
        log.error(
            f"The file ??{settings_path}?? could not be loaded. There is most "
            "likely a syntax error. Exiting."
            )
        sys.exit(1)

    check_settings(settings)
    plotting = False
    if settings.get("alphaplots"):
        code = check_alphaplots_requirements(settings)
        if code:
            venv = settings["alphaplots"].get("venv")
            log.error(
                "There was a problem with your alphaplots installation. Check "
                "the message produced py alphaplots above."
                )
            if venv:
                activate_path = Path(venv) / "bin" / "activate"
                log.warning(
                    "Before you install anything, make sure to activate the "
                    f"alphaplots-env with ??source {activate_path}??"
                    )
                log.warning(
                    "use ??deactivate?? after the installation and reactivate "
                    "the virtual environment (source ...) for alphabuddy if "
                    "you were using one."
                    )
            log.error("Aborting.")
            sys.exit(1)
        plotting = True

    while True:
        next_job = get_next_job(input_path)

        if next_job:
            if check_config(next_job, settings):
                job = create_alphafold_job(next_job, settings, args)
                job.generate_fasta()
                code = job.run_alphafold()
                if code:
                    move_job(next_job, "failed_jobs")
                else:
                    move_job(next_job, "done_jobs")
                    if plotting:
                        job.run_alphaplots(settings)
                    else:
                        job.alphaplots = False
                job.end_time = datetime.datetime.now()
                job.duration = job.end_time - job.start_time
                job.print_job_details()
            else:
                move_job(next_job, "failed_jobs")
        else:
            log.info("Waiting for jobs. CTRL+C for interruption.")
            while not yaml_from_input(input_path):
                time.sleep(3)


if __name__ == "__main__":
    main()
