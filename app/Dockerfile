FROM docker.m.daocloud.io/python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY kb ./kb
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .
EXPOSE 8101
CMD ["uvicorn", "kb.main:app", "--host", "0.0.0.0", "--port", "8101"]
