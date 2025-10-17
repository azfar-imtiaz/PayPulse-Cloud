resource "aws_lambda_layer_version" "google_genai_layer" {
  layer_name          = "google_genai_layer"
  filename            = "${path.module}/../../lambda_layers/google_genai/google_genai_layer.zip"
  source_code_hash    = filebase64sha256("${path.module}/../../lambda_layers/google_genai/google_genai_layer.zip")
  compatible_runtimes = ["python3.12"]
  description         = "Google Generative AI dependencies for Lambda functions"

  depends_on = [
    # Ensure the zip file exists before creating the layer
  ]
}