__version_info__ = (1, 0, 2)
__version__ = ".".join(map(str, __version_info__))
__author__ = "Jan Eberhage, Institute for Biophysical Chemistry, Hannover Medical School (eberhage.jan@mh-hannover.de)"

import os
import sys
import argparse
import yaml
import logging
import time
import datetime
import pathlib
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


class AlphaFoldJob:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.fasta_paths = os.path.join(
            self.output_dir, self.name, self.name + ".fasta"
        )
        log.info("Creating the following job:")
        for key, val in self.__dict__.items():
            log.info(key.ljust(35, " ") + ": " + str(val))

    def generate_fasta(self):
        pathlib.Path(os.path.join(self.output_dir, self.name)).mkdir(
            parents=True, exist_ok=True
        )
        with open(self.fasta_paths, "w") as f:
            for key, val in self.sequences.items():
                f.write(">" + key + "\n")
                f.write(val + "\n")

    def run_alphafold(self):
        subprocess_list = ["python3"]
        subprocess_list.append(
            os.path.join(
                self.alphafold_path, "alphafold-main", "docker", "run_docker.py"
            )
        )
        subprocess_list.append("--max_template_date=" + self.max_template_date)
        subprocess_list.append("--data_dir=" + self.data_dir)
        subprocess_list.append("--docker_user=" + self.docker_user)
        subprocess_list.append("--output_dir=" + self.output_dir)
        subprocess_list.append("--fasta_paths=" + self.fasta_paths)
        if hasattr(self, "model_preset"):
            subprocess_list.append("--model_preset=" + self.model_preset)
        if hasattr(self, "num_multimer_predictions_per_model"):
            subprocess_list.append(
                "--num_multimer_predictions_per_model="
                + str(self.num_multimer_predictions_per_model)
            )
        if hasattr(self, "models_to_relax"):
            subprocess_list.append("--models_to_relax=" + self.models_to_relax)

        af_process = subprocess.run(subprocess_list)
        return af_process.returncode

    def print_job_details(self):
        with open(os.path.join(self.output_dir, self.name, "alphabuddy_job_details.txt"), "w") as f:
            for key, val in self.__dict__.items():
                f.write(key + ": " + val + "\n")

def check_settings(settings):
    if not type(settings["versions"]) is dict:
        log.error(
            "The settings file seems to have a bad layout for the »versions«. It should be a dictionary. Exiting."
        )
        sys.exit(1)

    default_version = next(
        (
            version
            for version in settings["versions"].keys()
            if settings["versions"][version]["default"] == True
        ),
        None,
    )

    if not default_version:
        log.error(
            "No default version was chosen under »versions«/<version> in the settings. Exiting."
        )
        sys.exit(1)
    if not "data_dir" in settings["versions"][default_version]:
        log.error(
            "A »data_dir« has to be provided under »versions«/<version> in the settings. Exiting."
        )
        sys.exit(1)
    if not "path" in settings["versions"][default_version]:
        log.error(
            "A »path« has to be provided under »versions«/<version> in the settings. Exiting."
        )
        sys.exit(1)
    log.info("Found valid settings")


def get_next_job(path):
    jobs = [
        entry
        for entry in os.scandir(path)
        if entry.is_file()
        and (entry.name.endswith(".yaml") or entry.name.endswith(".yml"))
    ]
    jobs.sort(key=lambda x: os.path.getmtime(x))
    if not jobs:
        return False
    for job in jobs:
        job_dict = yaml.safe_load(open(job.path))
        if "urgent" in job_dict.keys() and job_dict["urgent"]:
            return job
    return jobs[0]


def check_config(job, settings):
    job_dict = yaml.safe_load(open(job.path))

    if "version" in job_dict and job_dict["version"] not in settings["versions"].keys():
        log.warning(
            f"The file »{job.path}« contains a value for the key »version« that is not included in your settings file. Skipping."
        )
        return False

    if not "sequences" in job_dict.keys():
        log.warning(
            f"The file »{job.path}« has no »sequences«. This is mandatory. Skipping."
        )
        return False
    if not type(job_dict["sequences"]) is dict:
        log.warning(
            f"The file »{job.path}« seems to have a bad layout for the »sequences«. It should be an indented dictionary. Skipping."
        )
        return False

    return True


def create_alphafold_job(job, settings, args):
    job_dict = yaml.safe_load(open(job.path))

    if not "version" in job_dict.keys():
        job_dict["version"] = next(
            i
            for i in settings["versions"].keys()
            if settings["versions"][i]["default"] == True
        )

    job_dict["data_dir"] = settings["versions"][job_dict["version"]]["data_dir"]
    job_dict["alphafold_path"] = settings["versions"][job_dict["version"]]["path"]

    if not "name" in job_dict.keys():
        job_dict["name"] = os.path.splitext(pathlib.Path(job.path).name)[0]

    if "docker_user" in settings.keys():
        job_dict["docker_user"] = settings["docker_user"]
    else:
        job_dict["docker_user"] = "root"

    if not "output_dir" in job_dict.keys():
        if "output_dir" in settings.keys():
            job_dict["output_dir"] = settings["output_dir"]
        else:
            job_dict["output_dir"] = os.path.join(args.directory, "results")

    if not "max_template_date" in job_dict.keys():
        job_dict["max_template_date"] = datetime.datetime.today().strftime("%Y-%m-%d")

    return AlphaFoldJob(**job_dict)


def move_job_to_failed(job, directory):
    failed_path = os.path.join(directory, "failed_jobs")
    if not os.path.exists(failed_path):
        os.mkdir(failed_path)
    os.rename(job.path, os.path.join(failed_path, job.name))
    log.info(f"Moving job to »{failed_path}«.")

def move_job_to_done(job, directory):
    done_path = os.path.join(directory, "done_jobs")
    if not os.path.exists(done_path):
        os.mkdir(done_path)
    os.rename(job.path, os.path.join(done_path, job.name))
    log.info(f"Moving job to »{done_path}«.")

def main():
    global log
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(CustomFormatter())
    log.addHandler(ch)

    parser = argparse.ArgumentParser(
        add_help=False,
        description="This script will run AlphaFold with the given sequences and configurations provided in the directory.",
    )
    parser.add_argument(
        "directory",
        metavar="<alphabuddy_dir>",
        help="Relative or absolute path to the alphabuddy directory",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="%(prog)s (" + __version__ + ") " + " by " + __author__,
    )
    parser.add_argument(
        "-h", "--help", action="help", help="show this help message and exit"
    )
    args = parser.parse_args()

    input_path = os.path.join(args.directory, "input")
    if not os.path.exists(input_path):
        log.error(f"»{os.path.abspath(input_path)}« was not found. Aborting")
        sys.exit(1)

    while True:
        settings_path = os.path.join(args.directory, "settings.yaml")
        if not os.path.exists(settings_path):
            log.error(
                f"The file »{settings_path}« is mandatory. Please provide the settings at this specific location."
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
                    move_job_to_failed(next_job, args.directory)
                else:
                    move_job_to_done(next_job, args.directory)
                    job.print_job_details()
            else:
                move_job_to_failed(next_job, args.directory)
        else:
            log.info("Waiting for jobs. CTRL+C for interuption.")
            while not [
                entry
                for entry in os.scandir(input_path)
                if entry.is_file()
                and (entry.name.endswith(".yaml") or entry.name.endswith(".yml"))
            ]:
                time.sleep(3)


if __name__ == "__main__":
    main()
