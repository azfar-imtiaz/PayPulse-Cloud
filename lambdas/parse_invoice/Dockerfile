FROM public.ecr.aws/lambda/python:3.9

RUN yum -y install gcc poppler-utils

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY src/ ${LAMBDA_TASK_ROOT}/

CMD ["lambda_function.lambda_handler"]