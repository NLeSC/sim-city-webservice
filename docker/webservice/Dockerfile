FROM nlesc/simcitywebservice

USER root
COPY ./config.ini /var/lib/simcity/sim-city-webservice/config.ini
RUN chown simcity:simcity /var/lib/simcity/sim-city-webservice/config.ini

USER simcity
