##What it Does##
Scale is a general algorithm processing framework for remote sensing data based on open source software components.  Scale acts as a scheduler for Apache Mesos focused on algorithm processing.  Scale leverages Docker for project management of algorithms and algorithm versions.  Scale provides heavy processing of terabytes of remote sensing data per day and decreases algorithm integration time from years to days.

### Contributing
Scale was developed at the National Geospatial-Intelligence Agency (NGA) in collaboration with [Ball Aerospace](http://www.ballaerospace.com/) and [Applied Information Sciences (AIS)](http://www.appliedis.com/). The government has "unlimited rights" and is releasing this software to increase the impact of government investments by providing developers with the opportunity to take things in new directions. The software use, modification, and distribution rights are stipulated within the Apache 2.0 license.

All pull request contributions to this project will be released under the Apache 2.0 or compatible license. Software source code previously released under an open source license and then modified by NGA staff is considered a "joint work" (see 17 USC § 101); it is partially copyrighted, partially public domain, and as a whole is protected by the copyrights of the non-government authors and must be released according to the terms of the original open source license.

### Quick Start
We've provided a vagrant and ansible setup to get you going quickly. Make sure vagrant, virtualbox, and ansible are installed then.
```
cd vagrant
vagrant up
```
This will download a centos7 base image and start 2 virtual machines, a master and a slave. You can add additional slaves by editing `Vagrantfile` and adding them to the `HOSTS` and `mesos-slaves` sections before doing the `vagrant up`. Ansible will be used to push the configuration out and can take a while to run. You make need to modify `ansible/group_vars/all` or `ansible/vagrant.yml` if you need to specify a local docker index, etc.
