# === Lambda layers for bcrypt, pyjwt, and common utils functions

data "klayers_package_latest_version" "bcrypt" {
  name   = "bcrypt"
  region = var.aws_region
}

resource "aws_lambda_layer_version" "utils_layer" {
  layer_name = "utils-layer"
  compatible_runtimes = ["python3.12"]
  filename = "../lambda_layers/common/utils_layer.zip"
  source_code_hash = filebase64sha256("../lambda_layers/common/utils_layer.zip")
}

resource "aws_lambda_layer_version" "pyjwt_layer" {
  layer_name = "pyjwt-layer"
  compatible_runtimes = ["python3.12"]
  filename = "../lambda_layers/jwt/pyjwt_layer.zip"
  source_code_hash = filebase64sha256("../lambda_layers/jwt/pyjwt_layer.zip")
}