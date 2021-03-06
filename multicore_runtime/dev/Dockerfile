FROM gcr.io/google_appengine/base

# Install Python and C dev libraries necessary to compile the most popular
# Python libraries.
RUN apt-get -q update && \
  apt-get install --no-install-recommends -y -q \
    build-essential python2.7 python2.7-dev python-setuptools \
    git mercurial libffi-dev libssl-dev libxml2-dev \
    libxslt1-dev libpq-dev libmysqlclient-dev libcurl4-openssl-dev \
    libjpeg-dev zlib1g-dev libpng12-dev && \
  apt-get clean && rm /var/lib/apt/lists/*_*

ADD https://github.com/GoogleCloudPlatform/appengine-python-vm-runtime/releases/download/v0.1/appengine-python-vm-runtime-0.1.tar.gz /home/vmagent/python-runtime.tar.gz

# To use a custom-built version of the runtime, comment out the above ADD
# command and instead use the following line:
# COPY appengine-python-vm-runtime-0.3.tar.gz /home/vmagent/python-runtime.tar.gz

RUN easy_install pip
RUN pip install --upgrade gunicorn==19.4.1 futures==3.0.3
RUN pip install /home/vmagent/python-runtime.tar.gz

EXPOSE 8080

RUN ln -s /home/vmagent/app /app
WORKDIR /app

ADD . /app

# Configure the entrypoint with Managed VMs-essential configuration like "bind",
# but leave the rest up to the config file.
ENTRYPOINT ["/usr/bin/env", "gunicorn", "-b", "0.0.0.0:8080", "google.appengine.vmruntime.wsgi:meta_app", "--log-file=-", "-c", "gunicorn.conf.py"]
