variable "region" {
  type    = string
  default = "ap-northeast-2"
}
variable "account_id" {
  type = string
}
variable "name" {
  type    = string
  default = "weather-slack-bot"
}

variable "param_slack_token_path" {
  type    = string
  default = "/weatherbot/slack_token"
}
variable "param_last_hash_path" {
  type    = string
  default = "/weatherbot/last_status_hash"
}

variable "city_lat" {
  type    = string
  default = "37.5665"
}
variable "city_lon" {
  type    = string
  default = "126.9780"
}
variable "timezone" {
  type    = string
  default = "Asia/Seoul"
}

variable "dry_run" {
  type    = string
  default = "false"
}
