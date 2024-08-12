source "yandex" "nebius" {
  disk_size_gb              = 30
  disk_type                 = "network-ssd"
  endpoint                  = "api.ai.nebius.cloud:443"
  folder_id                 = var.nebius_folder_id
  source_image_family       = "ubuntu-2204-lts"
  ssh_username              = "ubuntu"
  ssh_clear_authorized_keys = true
  subnet_id                 = var.nebius_subnet_id
  token                     = var.nebius_token
  use_ipv4_nat              = true
  zone                      = "eu-north1-c"
}
