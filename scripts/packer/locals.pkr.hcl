locals {
  clean_image_version = regex_replace(var.image_version, "[^a-z0-9-]", "-")
  image_name = "${var.build_prefix}dstack-${local.clean_image_version}"
  docker_version = ""
  cuda_drivers_version = ""
}
