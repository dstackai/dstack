build {
  # TODO: transition to this generic template from legacy per-backend JSON templates

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
    environment_vars = ["IMAGE_VERSION=${var.image_version}"]
    script           = "provisioners/pull-docker-images.sh"
  }
}
