FROM dragon/findmy-home:0.1.0
USER root
WORKDIR /src
COPY . /src
ENV PYTHONPATH=/src/findmy_home/rootfs/app
ENTRYPOINT []
CMD ["python","-m","unittest","discover","-s","tests","-v"]
