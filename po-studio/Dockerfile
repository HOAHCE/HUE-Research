# PO-Studio — paper-writing pipeline + web UI
FROM python:3.11-slim
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
# TeX Live with publisher classes (elsarticle, IEEEtran), XeLaTeX + fonts for Vietnamese
RUN apt-get update && apt-get install -y --no-install-recommends \
      texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
      texlive-publishers texlive-science texlive-bibtex-extra texlive-xetex texlive-lang-other \
      fonts-texgyre latexmk && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m po && mkdir -p /data/jobs && chown -R po /data /app
USER po
ENV POSTUDIO_JOBS_DIR=/data/jobs
EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
