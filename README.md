# Overview

Accelize AcceleratorAPI is a powerful and flexible toolkit for testing and operate FPGA accelerated function .

Some reasons you might want to use AcceleratorAPI :
+ Accelize AcceleratorAPI provides an abstraction layer to use the power of FPGA devices in a cloud environment. 
+ The configuration and the provisioning is generated for you in your CSP context (Keep your data on your Private Cloud)
+ Don't like python use one of the REST_API provided in most of the language to interact with the REST instance

## All the accelerated functions

AcceleratorAPI provides a variety of accelerated functions.

Browse our web site [AccelStore](https://accelstore.accelize.com), to discover them.

## Basic Python code example

Accelerator API is easy to use and only need few lines of codes for instantiate accelerator and CSP instance and then
 process files:

```python
import acceleratorAPI

# Choose an accelerator
with acceleratorAPI.AcceleratorClass(accelerator='cast_gzip') as myaccel:

    # Start and configure accelerator CSP instance
    myaccel.start()

    # Process files using FPGA
    myaccel.process(file_in='/path/myfile.dat',  file_out='/path/result.dat')
    myaccel.process(file_in='/path/myfile.dat',  file_out='/path/result.dat')
    # ... Process any number of file as needed
    
# By default, CSP instance is automatically close on "with" exit.
```

# Documentation

For more information acceleratorAPI, please read the [documentation](https://).

# Support and enhancement requests
[Contact us](https://www.accelize.com/contact) if you have any support or enhancement request.
