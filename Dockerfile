FROM continuumio/miniconda3

# Install mamba for faster dependency resolution
RUN conda install mamba -y -c conda-forge

ARG conda_env=pride_env
WORKDIR /app

COPY environment.yml ./
COPY config.ini ./
COPY *.py ./
#SHELL ["/bin/bash", "-c"]
RUN mamba env create -n $conda_env -f environment.yml

RUN echo "conda activate pride_env" >> ~/.bashrc

RUN /bin/bash -c "source ~/.bashrc"

# Add conda installation dir to PATH (instead of doing 'conda activate')
ENV PATH /opt/conda/envs/$conda_env/bin:$PATH

CMD [ "/bin/bash", "-c", "source ~/.bashrc && /bin/bash"]
ENTRYPOINT python pride-archive-usi.py -c PRODUCTION

#RUN source /opt/conda/etc/profile.d/conda.sh && conda init bash && bash && conda env create -n pride_env -f environment.yml
#ENTRYPOINT source /opt/conda/etc/profile.d/conda.sh && conda activate pride_env && python pride-archive-usi.py -c PRODUCTION