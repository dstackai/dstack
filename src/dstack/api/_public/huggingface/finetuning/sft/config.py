REPORT_TO_COMMANDS = {
    "wandb": ["pip install wandb"],
    "tensorboard": ["pip install tensorboard", "tensorboard --logdir results/runs &"],
}

REPORT_TO_PORTS = {"tensorboard": ["6006"]}
