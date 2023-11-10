build {
  source "source.yandex.nebius" {
    name = "nebius-cuda"
    image_description   = "Ubuntu 22.04 with CUDA, Docker and dstackai/base:cuda images"
    image_family        = "dstack-cuda"
    image_name          = "${local.image_name}-cuda"
  }
  # TODO(egor-s) add other sources

  provisioner "shell" {
    inline = ["cloud-init status --long --wait"]
  }

  provisioner "shell" {
    scripts = ["provisioners/kernel/apt-upgrade.sh", "provisioners/kernel/apt-daily.sh", "provisioners/kernel/apt-packages.sh", "provisioners/kernel/kernel-tuning.sh"]
  }

  provisioner "file" {
    destination = "/tmp/install-docker.sh"
    source      = "provisioners/install-docker.sh"
  }

  provisioner "file" {
    destination = "/tmp/run-docker"
    source      = "provisioners/run-docker"
  }

  provisioner "shell" {
    inline = ["cd /tmp", "chmod +x install-docker.sh", "./install-docker.sh --version ${local.docker_version}"]
  }

  provisioner "shell" {
    environment_vars = ["CUDA_DRIVERS_VERSION=${local.cuda_drivers_version}"]
    script           = "provisioners/cuda.sh"
  }

  provisioner "shell" {
    environment_vars = ["IMAGE_VERSION=${var.image_version}"]
    script           = "provisioners/docker-image-with-cuda.sh"
  }
}
