FROM public.ecr.aws/lambda/python:3.9

RUN yum -y install gcc poppler-utils

# Set working directory
WORKDIR /var/task

# Install requirements
COPY lambdas/parse_invoice/requirements.txt .
RUN pip3 install -r requirements.txt

# Copy lambda function source
COPY lambdas/parse_invoice/src/ .

# Copy common utils
COPY lambda_layers/common/python/utils/ utils/

CMD ["lambda_function.lambda_handler"]