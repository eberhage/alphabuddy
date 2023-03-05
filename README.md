# alphabuddy
Auto-Loader for Alphafold-Docker

## Usage:
Specify a working directory. This working directory needs to contain the file settings.yaml
```
python3 alphabuddy.py /path/to/working/directory
```

settings.yaml:
```
docker_user: root #(OPTIONAL)
output_dir: ./results #(OPTIONAL)
versions:
  version_1_name:
    path: /path/to/af/version/1/main-folder
    venv: /path/to/af/version/1/alphafold-env
    data_dir: /path/to/af/data_dir
    default: true
  my_very_long_version_2_name:
    path: /path/to/af/version/2/main-folder
    venv: /path/to/af/version/2/alphafold-env
    data_dir: /path/to/af/data_dir
    docker_image_name: alphafold-custum01 #(OPTIONAL)
alphaplots: #(OPTIONAL)
  path: /path/to/alphaplots.py #(OPTIONAL)
  venv: /path/to/alphaplots-env #(OPTIONAL)
```
settings.yaml has to contain at least one version under "versions". "path", "venv" and "data_dir" are mandatory and have to point to the corresponding AlphaFold ressources.

In the working directory, the directory "input" will be created. You can fill it with jobs:

job.yaml:
```
name: fancy_name #(OPTIONAL)
output_dir: ./results/custom_out_dir #(OPTIONAL)
urgent: false #(OPTIONAL)
version: my_very_long_version_2_name
model_preset: multimer #(OPTIONAL)
num_multimer_predictions_per_model: 2 #(OPTIONAL)
models_to_relax: all #(OPTIONAL)
max_template_date: 2123-01-02 #(OPTIONAL)
sequences:
  sequence_1: MGHKLMERRD
  sequence_2: TEST
  sequence_3: ANTHERTEST
alphaplots: #(OPTIONAL)
  - jsondump #(OPTIONAL)
  - rmpkl #(OPTIONAL)
```
The job-file needs to contain at least the sequences.

##Default values:
| Key                                   | Origin    | Default value |
| ---                                   | ---       | ---           |
| docker_user                           | settings  | root    |
| output_dir                            | settings  | ./results      |
| docker_image_name                     | settings  | the one provided in alphafold-main/docker/run_docker.py |
| alphaplots > venv                     | settings  | python3 (no venv) |
| output_dir                            | job       | value from settings     |
| name                                  | job       | name of job.yaml (without .yaml) |
| urgent                                | job       | false |
| version                               | job       | default version as specified in settings.yaml |
| model_preset                          | job       | monomer (from alphafold-main/docker/run_docker.py) |
| num_multimer_predictions_per_model    | job       | 5 (from alphafold-main/docker/run_docker.py) |
| models_to_relax                       | job       | best (from alphafold-main/docker/run_docker.py) |
| max_template_date                     | job       | today |

