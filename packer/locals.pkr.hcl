locals {
  clean_image_version = regex_replace(var.image_version, "[^a-z0-9-]", "-")
  image_name = "${var.build_prefix}dstack-${local.clean_image_version}"
  docker_version = "20.10.17"
  cuda_drivers_version = "535.54.03-1"
}
