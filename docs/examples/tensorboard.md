# Track experiments with TensorBoard 

This tutorial demonstrates how to use TensorBoard with `dstack` to track experiment metrics.

!!! info "NOTE:"
    The source code of this tutorial is available in the <a href="https://github.com/dstackai/dstack-playground#readme" target="__blank">Playground</a>.

## 1. Create the training script

TensorBoard is supported by all major training frameworks. Below, you will find the source code for a
`tutorials/tensorboard/train.py` script that uses PyTorch Lightning to train the model and save the logs to the local
lightning_logs folder.

??? info "Source code"
    
    To begin, we will create the training script `tutorials/tensorboard/train.py`.
    
    Our first step will be to define a `LightningDataModule`.
    
    ```python
    class MNISTDataModule(pl.LightningDataModule):
        def __init__(self, data_dir: Path = Path("data"), batch_size: int = 32, num_workers: int = os.cpu_count()):
            super().__init__()
            self.data_dir = data_dir
            self.batch_size = batch_size
            self.num_workers = num_workers
            self.transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))])
    
        def prepare_data(self):
            MNIST(self.data_dir, train=True, download=True)
            MNIST(self.data_dir, train=False, download=True)
    
        def setup(self, stage: Optional[str] = None):
            if stage == 'fit' or stage is None:
                mnist_full = MNIST(self.data_dir, train=True, transform=self.transform)
                self.mnist_train, self.mnist_val = random_split(mnist_full, [55000, 5000])
    
            if stage == 'test' or stage is None:
                self.mnist_test = MNIST(self.data_dir, train=False, transform=self.transform)
    
        def train_dataloader(self):
            return DataLoader(self.mnist_train, batch_size=self.batch_size, num_workers=self.num_workers)
    
        def val_dataloader(self):
            return DataLoader(self.mnist_val, batch_size=self.batch_size, num_workers=self.num_workers)
    
        def test_dataloader(self):
            return DataLoader(self.mnist_test, batch_size=self.batch_size, num_workers=self.num_workers)
    ```
    
    In order to log metrics at each epoch, we divide the data into `self.mnist_train` and `self.mnist_val`, and then we override
    the `val_dataloader` method to provide the validation dataloader that will be used during the validation step.
    
    We can now define the `LightningModule`.
    
    ```python hl_lines="32-41"
    class LitMNIST(pl.LightningModule):
        def __init__(self, hidden_size=64, learning_rate=2e-4):
            super().__init__()
            self.hidden_size = hidden_size
            self.learning_rate = learning_rate
    
            self.num_classes = 10
            channels, width, height = (1, 28, 28)
    
            self.model = nn.Sequential(
                nn.Flatten(),
                nn.Linear(channels * width * height, hidden_size),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_size, hidden_size),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_size, self.num_classes),
            )
    
            self.accuracy = Accuracy('multiclass', num_classes=10)
    
        def forward(self, x):
            return self.model(x)
    
        def training_step(self, batch, batch_idx):
            x, y = batch
            logits = self(x)
            loss = F.cross_entropy(logits, y)
            return loss
    
        def validation_step(self, batch, batch_idx):
            x, y = batch
            logits = self(x)
            loss = F.cross_entropy(logits, y)
            preds = torch.argmax(logits, dim=1)
            self.accuracy(preds, y)
    
            self.log('val_loss', loss, prog_bar=True)
            self.log('val_acc', self.accuracy, prog_bar=True)
            return loss
    
        def test_step(self, batch, batch_idx):
            return self.validation_step(batch, batch_idx)
    
        def configure_optimizers(self):
            optimizer = torch.optim.Adam(self.parameters(), lr=self.learning_rate)
            return optimizer
    ```
    
    We override the `validation_step` method to log validation metrics using the `self.log` method.
    
    Finally, let's define the `main` function that puts everything together.
    
    ```python hl_lines="5-6 11"
    def main():
        dm = MNISTDataModule()
        model = LitMNIST()
    
        tqdm_bar = TQDMProgressBar(refresh_rate=20)
        early_stop = EarlyStopping(monitor="val_loss", patience=10, mode="min")
    
        trainer = pl.Trainer(
            accelerator="auto",
            devices="auto",
            callbacks=[tqdm_bar, early_stop],
            max_epochs=100,
        )
        trainer.fit(model, datamodule=dm)
        trainer.test(datamodule=dm, ckpt_path='best')
    ```
    
    For convenience, we utilize the `TQDMProgressBar` and `EarlyStopping` callbacks. The former provides interactive output,
    while the latter automatically stops training if the target metric no longer improves.



## 2. Define the workflow file

Create the following YAML file:

<div editor-title=".dstack/workflows/tensorboard.yaml"> 

```yaml
workflows:
  - name: train-tensorboard
    provider: bash
    ports:
      - port 6006
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - tensorboard --port 6006 --host 0.0.0.0 --logdir ./lightning_logs &
      - python tutorials/tensorboard/train.py
    artifacts:
      - path: ./lightning_logs
```

</div>

Here's what the workflow above does:

1. It launches the `tensorboard` application as a background process and direct it to the `lightning_logs` folder, where
the training script will write event logs.

2. The workflow requests a port from `dstack` and passes it to `tensorboard`. This allows us
to access the TensorBoard application while the workflow is running.

3. Finally, itssave the `lightning_logs` folder as an output artifact so that we can access the logs after the workflow has
finished.

## 3. Run the workflow

!!! info "NOTE:"
    Before running the workflow, make sure that you have set up the Hub application and
    [created a project](../docs/quick-start.md#create-a-hub-project) that can run workflows in the cloud.

Once the project is configured, we can use the [`dstack run`](../docs/reference/cli/run.md) command to
run our workflow.

!!! info "NOTE:"
    The Hub will automatically create the corresponding cloud resources, run the application, and forward the application
    port to localhost. If the workflow is completed, it automatically destroys the cloud resources.

<div class="termy">

```shell
$ dstack run train-tensorboard

RUN      WORKFLOW           SUBMITTED  STATUS     TAG  BACKENDS
snake-1  train-tensorboard  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

TensorBoard 2.12.0 at http://127.0.0.1:51623/ (Press CTRL+C to quit)

Downloading http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz
---> 100%

GPU available: False, used: False

Epoch 1:  0% 0/1719 [00:05<00:09, 108.99it/s, v_num=0, val_loss=0.126, val_acc=0.964]
...
```

</div>

By clicking on the TensorBoard URL in the output, we can monitor the metrics in real-time as the training progresses.

![tensorboard](../assets/images/dstack-tensorboard.png){ width=800 }

If you're running the workflow locally, its output artifacts are stored in the `~/.dstack/artifacts` directory. As a result, you
can run the `tensorboard` CLI on your local machine and point it to the corresponding folder to view the logs at any time
later.

<div class="termy">

```shell
$ tensorboard --logdir=~/.dstack/artifacts/github.com/dstack-playground/snake-1,train-tensorboard,0/lightning_logs
```

</div>

If you're running the workflow in the cloud, you can use the `dstack cp` command to copy remote artifacts to a 
local folder:

<div class="termy">

```shell
$ tensorboard cp snake-1 ./artifacts

---> 100%
```

</div>