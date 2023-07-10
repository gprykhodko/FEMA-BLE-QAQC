import os

class ToolValidator:
  # Class to add custom behavior and properties to the tool and tool parameters.

    def __init__(self):
        # set self.params for use in other function
        self.params = arcpy.GetParameterInfo()

    def initializeParameters(self):
        # Customize parameter properties. 
        # This gets called when the tool is opened.
        return

    def updateParameters(self):
        # Modify parameter values and properties.
        # This gets called each time a parameter is modified, before 
        # standard validation.
        return

    def updateMessages(self):
        # Customize messages for the parameters.
        # This gets called after standard validation.
        if self.params[3].value or self.params[3].altered:
            try:
                out_dir = os.path.normpath(self.params[3].valueAsText)
                iocheck_file = os.path.join(out_dir,"iocheck.txt")
                with open(iocheck_file,"w") as out:
                    out.write("\n")
                out.close()
                os.remove(iocheck_file)
                self.params[3].clearMessage()         
            except Exception:
                self.params[3].setErrorMessage("Specified output folder does not have write permission. Please select output folder location that has write permission.")
        return

    def isLicensed(self):
        # Check if Spatial Analyst is Available
        try:
            if arcpy.CheckExtension("Spatial") != "Available":
                raise Exception
        except Exception:            
            return False

        # Check if 3D Analyst is Available
        try:
            if arcpy.CheckExtension("3D") != "Available":
                raise Exception
        except Exception:            
            return False
        
        return True
