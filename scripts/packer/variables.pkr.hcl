variable "build_prefix" {
  type    = string
  default = ""
}

variable "image_version" {
  type = string
}

# Nebius
variable "nebius_folder_id" {
  type      = string
  default   = null
  sensitive = true
}

variable "nebius_subnet_id" {
  type      = string
  default   = null
  sensitive = true
}

variable "nebius_token" {
  type      = string
  default   = null
  sensitive = true
}
