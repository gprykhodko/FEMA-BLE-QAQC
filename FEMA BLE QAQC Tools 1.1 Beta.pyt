# -*- coding: utf-8 -*-
########################################################################################
# Toolbox Name: FEMA BLE QAQC Tools 1.1 Beta
# Version: 1.1 Beta
# Release date: 06/28/23
# Use: 
#               
#                   
# Author: Gennadii Prykhodko, Sam Sarkar, Halff Accociates, Inc., 2023
########################################################################################

import arcpy, os, zipfile, re, sys
import pandas as pd
import numpy as np
from arcgis.gis import GIS



class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "FEMA BLE QAQC Tools 1.1 Beta"
        self.alias = "FEMABLEQAQCToolsBeta"

        # List of tool classes associated with this toolbox
        self.tools = [FeatureSchemaCheck, ComparisonToFEMAEffective, MappingValueCheck, WaterbodiesCheck, FloodHazardAreaCheck]        

class TestControl:
    def __init__(self, items, attributes, schema, null_values, features, rasters):
        self.items = items
        self.attributes = attributes
        self.schema = schema
        self.null_values = null_values
        self.features = features
        self.rasters = rasters

class FeatureSchemaCheck(object):

    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "1. Feature, Schema Check"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(displayName="Flood Risk Database",name="Flood_Risk_Database",datatype="DEWorkspace",parameterType="Required",direction="Input")
        param1 = arcpy.Parameter(displayName="Flood Risk Database Schema",name="Flood_Risk_Database_Schema",datatype="DEFile",parameterType="Required",direction="Input")
        param2 = arcpy.Parameter(displayName="QAQC Report Folder",name="QAQC_Report_Folder",datatype="DEFolder",parameterType="Required",direction="Input")
        param3 = arcpy.Parameter(displayName="Report File",name="Report_File",datatype="DETextFile",parameterType="Derived",direction="Output")
        param0.filter.list = ['Local Database']
        param1.filter.list = ['xml']
        params = [param0, param1, param2, param3]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""

        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        self.check_folder_permission(parameters[2])
        if not str(parameters[0].value).endswith('.gdb'):
            parameters[0].setErrorMessage('Not a file geodatabase')
        if not str(parameters[1].value).endswith('.xml'):
            parameters[1].setErrorMessage('BLE schema has to be in .xml format')
        return
    
    def check_folder_permission(self, parameter):
        if parameter.value or parameter.altered:
            try:
                out_dir = os.path.normpath(parameter.valueAsText)
                iocheck_file = os.path.join(out_dir,"iocheck.txt")
                with open(iocheck_file,"w") as out:
                    out.write("\n")
                out.close()
                os.remove(iocheck_file)
                parameter.clearMessage()         
            except Exception:
                parameter.setErrorMessage("Specified output folder does not have write permission. Please select output folder location that has write permission.")

    def execute(self, parameters, messages):
        """The source code of the tool."""

        in_gdb = parameters[0].valueAsText
        schema_xml = parameters[1].valueAsText
        out_folder = parameters[2].valueAsText
        
        report_name = 'QAQC_Report_' + os.path.basename(in_gdb).split('.')[0][8:] + '.txt'
        report_file = os.path.join(out_folder, report_name)
        parameters[3].value = report_file
        fema_portal = r"https://fema.maps.arcgis.com/"
        item_id = '491035bd63624dd6b7181016736c4da6'
        arcpy.env.workspace = in_gdb
        scratch_gdb = arcpy.env.scratchWorkspace

        # Environment Settings
        arcpy.env.overwriteOutput = True
        arcpy.env.addOutputsToMap = False

        arcpy.SetProgressorLabel("Reading BLE database schema....")
        arcpy.AddMessage("Reading BLE database schema....")

        arcpy.management.CreateFileGDB(os.path.dirname(scratch_gdb), "ble_schema", "CURRENT")
        arcpy.management.ImportXMLWorkspaceDocument(os.path.join(os.path.dirname(scratch_gdb), "ble_schema.gdb"), schema_xml, "DATA", '')

        control_frd = os.path.join(os.path.dirname(scratch_gdb), "ble_schema.gdb")

        self.frd_check(report_file,in_gdb,fema_portal,scratch_gdb,item_id,in_gdb,control_frd)
        arcpy.management.Delete(os.path.join(os.path.dirname(scratch_gdb), "ble_schema.gdb"))
        #arcpy.SetParameterAsText(2, report_file)
        arcpy.AddMessage("Feature, schema check is complete....")
        arcpy.AddMessage(f'Report file path: {report_file}')
        return
    
    def unzip_data(self, portal, item_id, report_file):
        try:     
            #downloads_path = str(Path.home() / "Downloads")    # path to downloads folder
            data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
            if os.path.isdir(data_dir):
                downloaded_gdb = os.path.join(data_dir, 'BLE-QAQC-Tools-Data.gdb')
            else:
                arcpy.SetProgressorLabel("Downloading required data....")
                arcpy.AddMessage("Downloading required data....")
                gis = GIS(portal)
                tool_data = gis.content.get(item_id)
                os.makedirs(data_dir)
                zipped_tool_data = tool_data.download(data_dir)    # download the data item
                z = zipfile.ZipFile(zipped_tool_data)
                z.extractall(data_dir)
                downloaded_gdb = os.path.join(data_dir, 'BLE-QAQC-Tools-Data.gdb')  
            return downloaded_gdb     
        except Exception as e:
            msg = f'Error downloading required data: {e}'
            arcpy.AddError(msg)
            sys.exit(msg)

    def parse_gdb(self, in_frd):
        arcpy.env.workspace = in_frd
        feature_datasets = arcpy.ListDatasets({}, "Feature")
        raster_datasets = arcpy.ListDatasets({}, "Raster")
        tables = arcpy.ListTables()
        features = [(ds, fc) for ds in feature_datasets for fc in arcpy.ListFeatureClasses(feature_dataset = ds)]
        rasters = [(raster, raster) for raster in raster_datasets]
        tables = [("NA", table) for table in tables]
        frd_items = features + rasters + tables
        
        null_values = {}
        db_items = {}
        for i in features:
            print(i[0],'\\', i[1])
            fc = os.path.join(in_frd, i[0], i[1])
            try:
                arr = arcpy.da.FeatureClassToNumPyArray(fc, "*")
                db_items[i] = arr.dtype.descr
            except:
                print(i[0] + '\\' + i[1] + ' has null values and could not be processed')
                arr = arcpy.da.FeatureClassToNumPyArray(fc, "*", skip_nulls=True)
                db_items[i] = arr.dtype.descr
                null_values[i] = arr.dtype.descr
        for i in tables:
            print(i[0],'\\', i[1])
            table = os.path.join(in_frd, i[1])
            try:
                arr = arcpy.da.TableToNumPyArray(table, "*")
                db_items[i] = arr.dtype.descr
            except:
                print(i[0] + '\\' + i[1] + ' is has null values and could not be processed')
                arr = arcpy.da.TableToNumPyArray(table, "*", skip_nulls=True)
                db_items[i] = arr.dtype.descr
                null_values[i] = arr.dtype.descr
                
        db_attributes = {}
        db_schema = {}
        for key, value in db_items.items():
            #print(control_attributes[key])
            attributes = [attribute[0] for attribute in db_items[key]]
            db_attributes[key] = attributes
            schema = [attribute[1] for attribute in db_items[key]]
            db_schema[key] = schema
        return TestControl(frd_items, db_attributes, db_schema, null_values, features, rasters)
        
    def frd_check(self, report_file, in_gdb, fema_portal, scratch_gdb, item_id, test_gdb, base_gdb):
            arcpy.SetProgressorLabel("Reading geodatabase items....")
            arcpy.AddMessage("Reading geodatabase items....")

            control = self.parse_gdb(base_gdb)

            test = self.parse_gdb(test_gdb)
            
            arcpy.SetProgressorLabel("Performing feature and schema check....")
            arcpy.AddMessage("Performing feature and schema check....")

            not_in_db = list(set(control.items) - set(test.items))
            extra_in_db = list(set(test.items) - set(control.items))
            
            df = pd.DataFrame(control.items, columns=['Dataset', 'Item Name'])
            df['Present'] = "Yes"
            df['Missing Attributes'] = "No"
            df['Extra Attributes'] = "No"
            df['Schema Correct'] = 'Yes'
            df['None Acceptable Values'] = 'No'
            df['Clipped to HUC8 Boundary'] = 'NA'
            df.loc[df['Item Name'].isin([i[1] for i in test.rasters]), ["Missing Attributes", "Extra Attributes", "Schema Correct", "None Acceptable Values"]] = "NA"
            
            key_error = []
            for key, value in control.schema.items():
                try:
                    missing_attributes = list(set(control.attributes[key]) - set(test.attributes[key]))
                    extra_attributes = list(set(test.attributes[key]) - set(control.attributes[key]))
                    schema_error = list(set(control.schema[key]) - set(test.schema[key]))
                except KeyError as ke:
                    key_error.append(ke.args[0])
                    print(key_error)
                try:
                    if len(missing_attributes) == 1:
                        print(f'There is {len(missing_attributes)} attribute missing in the {key[1]} feature class')
                        print(missing_attributes[0]) #missing attribute
                        df["Missing Attributes"][df['Item Name'] == key[1]] = missing_attributes[0]
                    elif len(missing_attributes) > 1:
                        print(f'There are {len(missing_attributes)} attributes missing in the {key[1]} feature class')
                        print(', '.join([attribute for attribute in missing_attributes]))
                        df["Missing Attributes"][df['Item Name'] == key[1]] = ', '.join([attribute for attribute in missing_attributes])
                    if len(extra_attributes) == 1:
                        print(f'There is {len(extra_attributes)} attribute extra in the {key[1]} feature class')
                        print(extra_attributes[0]) #extra attribute
                        df["Extra Attributes"][df['Item Name'] == key[1]] = extra_attributes[0]
                    elif len(extra_attributes) > 1:
                        print(f'There are {len(extra_attributes)} attributes extra in the {key[1]} feature class')
                        print(', '.join([attribute for attribute in extra_attributes]))
                        df["Extra Attributes"][df['Item Name'] == key[1]] = ', '.join([attribute for attribute in extra_attributes])
                    if len(schema_error) == 1:
                        print(f'There is {len(schema_error)} schema error in the {key[1]} feature class')
                        df["Schema Correct"][df['Item Name'] == key[1]] = 'No'
                    elif len(schema_error) > 1:
                        print(f'There are {len(schema_error)} schema errors in the {key[1]} feature class')
                        df["Schema Correct"][df['Item Name'] == key[1]] = 'No'
                except:
                    msg = "Oops...Something went wrong. Contact support"
                    arcpy.AddError(msg)
                    sys.exit(msg)       
            if len(not_in_db) > 1:
                print(f'There are {len(not_in_db)} items missing in the database\n')
                df["Present"][df['Item Name'].isin([i[1] for i in not_in_db])] = 'No'
            elif len(not_in_db) == 1:
                print(f'There is {len(not_in_db)} item missing in the database')
                df["Present"][df['Item Name'] == not_in_db[0][1]] = 'No'
            if len(key_error) > 0:
                for i in key_error:
                    df.loc[(df["Present"] == "Yes") & (df["Item Name"] == i[1]), ["Missing Attributes", "Extra Attributes", "Schema Correct", "None Acceptable Values"]] = "Feature class could not be read" # rows with errors
                    df.loc[(df["Present"] == "No") & (df["Item Name"] == i[1]), ["Missing Attributes", "Extra Attributes", "Schema Correct", "None Acceptable Values"]] = "NA"
                    df.loc[(df["Present"] == "No") & (df["Item Name"] == i[1]), ["Missing Attributes", "Extra Attributes", "Schema Correct", "None Acceptable Values"]] = "NA"
            if len(test.null_values) > 0:
                for i in test.null_values:
                    df.loc[(df["Present"] == "Yes") & (df["Item Name"] == i[1]), ["None Acceptable Values"]] = "Yes"
                
            if 'S_HUC_Ar' in [i[1] for i in test.features]:
                huc8_index = [i[1] for i in test.features].index('S_HUC_Ar')
                test_feature = os.path.join(in_gdb, test.features[huc8_index][0], test.features[huc8_index][1])
                huc_sr = arcpy.Describe(test_feature).spatialReference
                wbdhu8 = os.path.join(self.unzip_data(fema_portal, item_id, report_file), 'WBDHU8')
                arcpy.SetProgressorLabel("Performing spatial check....")
                arcpy.AddMessage("Performing spatial check....")
                huc8_layer = arcpy.MakeFeatureLayer_management(wbdhu8, "WBDHU8")
                huc8_layer = arcpy.management.SelectLayerByLocation(huc8_layer.getOutput(0), "HAVE_THEIR_CENTER_IN", test_feature, "-1 Miles", "NEW_SELECTION", "NOT_INVERT")
                with arcpy.EnvManager(outputCoordinateSystem=huc_sr):
                    base_feature = arcpy.conversion.FeatureClassToFeatureClass(huc8_layer.getOutput(0), scratch_gdb, "HUC8_BaseFeatureX")
                for i in test.features:
                    if i[1] in [i[1] for i in control.items]:
                        fc = os.path.join(in_gdb, i[0], i[1])
                        row_count = [row[0] for row in arcpy.da.SearchCursor(fc, 'OID@')]
                        arcpy.AddMessage(f'{i[1]}')
                        fc_type = arcpy.Describe(fc).shapeType
                        if (row_count and fc_type == 'Point'):
                            arcpy.AddMessage(f'{i[1]}')
                            fc_layer = arcpy.MakeFeatureLayer_management(fc, i[1])
                            fc_layer = arcpy.management.SelectLayerByLocation(fc_layer.getOutput(0), "COMPLETELY_WITHIN", base_feature, None, "NEW_SELECTION", "INVERT")
                            not_clipped = fc_layer.getOutput(0).getSelectionSet()
                        if (row_count and fc_type in ['Polyline', 'Polygon']):
                            #arcpy.AddMessage(f'{fc_type} - {i[1]}')
                            fc_layer = arcpy.MakeFeatureLayer_management(fc, i[1])
                            fc_layer = arcpy.management.SelectLayerByLocation(fc_layer.getOutput(0), "CROSSED_BY_THE_OUTLINE_OF", base_feature, None, "NEW_SELECTION", "NOT_INVERT")
                            not_clipped = fc_layer.getOutput(0).getSelectionSet()
                        if not row_count:
                            #arcpy.AddMessage(f'Empty - {i[1]}')
                            df['Clipped to HUC8 Boundary'][df['Item Name'] == i[1]] = 'No'
                        elif not_clipped:
                            df['Clipped to HUC8 Boundary'][df['Item Name'] == i[1]] = 'No'
                        else: df['Clipped to HUC8 Boundary'][df['Item Name'] == i[1]] = 'Yes'
                huc_compare = arcpy.management.FeatureCompare(base_feature, test_feature, "OBJECTID", "GEOMETRY_ONLY", "IGNORE_M;IGNORE_Z;IGNORE_POINTID;IGNORE_EXTENSION_PROPERTIES;IGNORE_SUBTYPES;IGNORE_RELATIONSHIPCLASSES;IGNORE_REPRESENTATIONCLASSES;IGNORE_FIELDALIAS", "0.000000784415 DecimalDegrees", 0.001, 0.003280833333, None, None, "CONTINUE_COMPARE")
                message = huc_compare.getMessages(1)
                if 'Geometries are different' in message:
                    print('S_HUC_AR does not align to USGS HUC8 Boundary')
                    huc_compare = 'S_HUC_AR does not align to USGS HUC8 Boundary'
                    df['Clipped to HUC8 Boundary'][df['Item Name'] == 'S_HUC_Ar'] = 'No'
                else: 
                    print('S_HUC_AR aligns to USGS HUC8 Boundary')
                    huc_compare = 'S_HUC_AR aligns to USGS HUC8 Boundary'
                    df['Clipped to HUC8 Boundary'][df['Item Name'] == 'S_HUC_Ar'] = 'Yes'
                df.to_csv(report_file, sep='\t', index=False)
                with open(report_file, "a") as report:
                    report.write('-----------------------------------------------\nTool 1 - Results:\n-----------------------------------------------')
                    report.write(f'\n{huc_compare}')
                arcpy.management.Delete(base_feature)
        
            if len(not_in_db) > 1:
                #df.to_csv(report_file, sep='\t', index=False)
                with open(report_file, "a") as report:
                    report.write(f'\nThere are {len(not_in_db)} items missing in the database:\n' +
                                '\n'.join(['/'.join(item) for item in not_in_db]))
            elif len(not_in_db) == 1:
                #df.to_csv(report_file, sep='\t', index=False)
                with open(report_file, "a") as report:
                    report.write(f'\nThere is {len(not_in_db)} item missing in the database:\n' +
                                '\n'.join(['/'.join(item) for item in not_in_db]))
            elif len(not_in_db) == 0:
                
                with open(report_file, "a") as report:
                    report.write(f'\nThere are {len(not_in_db)} items missing in the database')
            if len(extra_in_db) == 1:
                with open(report_file, "a") as report:
                    report.write(f'\nThere is {len(extra_in_db)} extra item in the database:\n' +
                                '\n'.join(['/'.join(item) for item in extra_in_db]))
            elif len(extra_in_db) > 0:
                with open(report_file, "a") as report:
                    report.write(f'\nThere are {len(extra_in_db)} extra items in the database:\n' +
                                '\n'.join(['/'.join(item) for item in extra_in_db]))
            if len(test.null_values) > 0:
                for i in test.null_values:
                    if i[1] in [i[1] for i in control.items]:
                        with open(report_file, "a") as report:
                            report.write(f'\n{i[1]} has null values')
            return test.features

class ComparisonToFEMAEffective(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "2. Comparison to FEMA Effective"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(displayName="Flood Risk Database",name="Flood_Risk_Database",datatype="DEWorkspace",parameterType="Required",direction="Input")
        param1 = arcpy.Parameter(displayName="QAQC Report Folder",name="QAQC_Report_Folder",datatype="DEFolder",parameterType="Required",direction="Input")
        params = [param0, param1]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        if not str(parameters[0].value).endswith('.gdb'):
            parameters[0].setErrorMessage('Not a file geodatabase')
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        in_gdb = parameters[0].valueAsText
        out_folder = parameters[1].valueAsText
        
        report_name = 'QAQC_Report_' + os.path.basename(in_gdb).split('.')[0][8:] + '.txt'
        report_file = os.path.join(out_folder, report_name)
        #parameters[3].value = report_file
        fema_portal = r"https://fema.maps.arcgis.com/"
        item_id = '491035bd63624dd6b7181016736c4da6'
        arcpy.env.workspace = in_gdb
        scratch_gdb = arcpy.env.scratchWorkspace


        # Environment Settings
        arcpy.env.overwriteOutput = True
        arcpy.env.addOutputsToMap = False

        feature_datasets = arcpy.ListDatasets({}, "Feature")
        features = [(ds, fc) for ds in feature_datasets for fc in arcpy.ListFeatureClasses(feature_dataset = ds)]
        if 'DTL_STUD_AR' or 'DTL_STUD_LN' in [i[1] for i in features]:
            with open(report_file, "a") as report:
                report.write('\n-----------------------------------------------\nTool 2 - Results:\n-----------------------------------------------')
        if 'DTL_STUD_AR' in [i[1]  for i in features]:
            self.nfhl_compare('DTL_STUD_AR','polygons',report_file,features,in_gdb,fema_portal,item_id,scratch_gdb)
        if 'DTL_STUD_LN' in [i[1] for i in features]:
            self.nfhl_compare('DTL_STUD_LN','lines',report_file,features,in_gdb,fema_portal,item_id,scratch_gdb)
        with open(report_file, "a") as report:
            report.write('\nManual review of DTL_STUD_AR polygons compared to BLE extents required')
        #arcpy.SetParameterAsText(2, report_file)
        arcpy.AddMessage('Comaprison to FEMA effective is complete.....')
        arcpy.AddMessage(f'Report file path: {report_file}')
        with arcpy.EnvManager(workspace = arcpy.env.scratchWorkspace):
            to_delete = arcpy.ListFeatureClasses("*X")
            for fc in to_delete:
                arcpy.management.Delete(os.path.join(arcpy.env.scratchWorkspace, fc))
        if 'DTL_STUD_AR' and 'DTL_STUD_LN' not in [i[1] for i in features]: 
            arcpy.AddMessage('There are no detailed studies features in the database.....')
        return

    def create_gdb(self,data_dir,report_file):
        gdb_name = os.path.basename(report_file)[:-4]
        if os.path.isdir(os.path.join(data_dir, gdb_name+'.gdb')):            
            gdb_path = os.path.join(data_dir, gdb_name+'.gdb')
        else:            
            gdb_name = os.path.basename(report_file)[:-4]
            gdb_path = arcpy.management.CreateFileGDB(data_dir, gdb_name)
            gdb_path = gdb_path.getOutput(0)
        return gdb_path

    # Download and extract the data
    def unzip_data(self,portal,item_id,report_file):
        arcpy.SetProgressorLabel('Getting FEMA effective data...')
        arcpy.AddMessage('Getting FEMA effective data...')
        try:     
            #downloads_path = str(Path.home() / "Downloads")    # path to downloads folder
            data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
            if os.path.isdir(data_dir):
                downloaded_gdb = os.path.join(data_dir, 'BLE-QAQC-Tools-Data.gdb')
            else:
                gis = GIS(portal)
                tool_data = gis.content.get(item_id)
                os.makedirs(data_dir)
                zipped_tool_data = tool_data.download(data_dir)    # download the data item
                z = zipfile.ZipFile(zipped_tool_data)
                z.extractall(data_dir)
                downloaded_gdb = os.path.join(data_dir, 'BLE-QAQC-Tools-Data.gdb')       
        except Exception as e:
            arcpy.AddMessage(f'Error unzipping file: {e}')
        return downloaded_gdb

    def nfhl_compare(self,test_feature,feature_type,report_file,features,in_gdb,fema_portal,item_id,scratch_gdb):
        data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
        save_path = self.create_gdb(data_dir,report_file)
        try: 
            huc8_index = [i[1] for i in features].index('S_HUC_Ar')
            huc8_feature = os.path.join(in_gdb, features[huc8_index][0], features[huc8_index][1])
        except:
            huc8_feature = os.path.join(self.unzip_data(fema_portal,item_id,report_file), 'WBDHU8')
            huc8_layer = arcpy.MakeFeatureLayer_management(huc8_feature, "WBDHU8")
            huc8_layer = arcpy.management.SelectLayerByLocation(huc8_layer.getOutput(0), "INTERSECT", test_feature, "-1 Miles", "NEW_SELECTION", "NOT_INVERT")
            test_feature_sr = arcpy.Describe(test_feature).spatialReference
            with arcpy.EnvManager(outputCoordinateSystem=test_feature_sr):
                huc8_feature = arcpy.conversion.FeatureClassToFeatureClass(huc8_layer, scratch_gdb, "HUC8_BaseFeatureX")
        test_index = [i[1] for i in features].index(test_feature)
        test_feature = os.path.join(in_gdb, features[test_index][0], features[test_index][1])
        huc_sr = arcpy.Describe(huc8_feature).spatialReference
        
        with arcpy.EnvManager(workspace = arcpy.env.scratchWorkspace):
            if arcpy.Exists(os.path.join(scratch_gdb, "NFHL_ProjectX")):
                nfhl_project = os.path.join(scratch_gdb, "NFHL_ProjectX")
            if arcpy.Exists(os.path.join(scratch_gdb, "NFHL_ClipedX")):
                nfhl_clip = os.path.join(scratch_gdb, "NFHL_ClipedX")
            else:
                nfhl_fl = os.path.join(self.unzip_data(fema_portal,item_id,report_file), 'NFHL')
                nfhl_project = arcpy.management.Project(nfhl_fl, os.path.join(scratch_gdb, "NFHL_ProjectX"), huc_sr, None, None, "NO_PRESERVE_SHAPE", None, "NO_VERTICAL")
                nfhl_clip = arcpy.analysis.PairwiseClip(nfhl_project, huc8_feature, os.path.join(scratch_gdb, "NFHL_ClipedX"), None)
        #message = nfhl_clip.getMessages(1)
        #if 'empty output' in message:
            #nfhl_compare = 'There are no detailed studies in this watershed'
            #print(message)
        dtl_layer = arcpy.management.MakeFeatureLayer(test_feature, os.path.basename(test_feature))
        nfhl_layer = arcpy.management.MakeFeatureLayer(nfhl_clip, "NFHL_Clipped")
        arcpy.SetProgressorLabel(f"Comparing {os.path.basename(test_feature)} to FEMA effective....")
        arcpy.AddMessage(f"Comparing {os.path.basename(test_feature)} to FEMA effective....")
        compare_layer = arcpy.management.SelectLayerByLocation(dtl_layer.getOutput(0), "INTERSECT", nfhl_layer.getOutput(0), None, "NEW_SELECTION", "NOT_INVERT")
        dtl_count = len(compare_layer.getOutput(0).getSelectionSet())
        nfhl_count = arcpy.management.GetCount(nfhl_clip).outputCount
        df = pd.read_csv(report_file, '\t')
        if dtl_count == nfhl_count:
            nfhl_compare = f'There are no missing {os.path.basename(test_feature)} {feature_type} in the database'
            df.loc[df["Item Name"] == os.path.basename(test_feature), 'NFHL Spatial Check'] = 'Pass'
            print(nfhl_compare)
        elif dtl_count > nfhl_count:
            arcpy.conversion.FeatureClassToFeatureClass(nfhl_clip, save_path, f'{os.path.basename(test_feature)}_Check')
            nfhl_compare = f'There are {dtl_count - nfhl_count} extra {os.path.basename(test_feature)} {feature_type} in the database. See Supplemental Data feature {os.path.basename(test_feature)}_Check'
            df.loc[df["Item Name"] == os.path.basename(test_feature), 'NFHL Spatial Check'] = 'Fail'
            print(nfhl_compare)
        elif dtl_count < nfhl_count:
            arcpy.conversion.FeatureClassToFeatureClass(nfhl_clip, save_path, f'{os.path.basename(test_feature)}_Check')
            nfhl_compare = f'There are {nfhl_count - dtl_count} missing {os.path.basename(test_feature)} {feature_type} in the database. See Supplemental Data feature {os.path.basename(test_feature)}_Check'
            df.loc[df["Item Name"] == os.path.basename(os.path.basename(test_feature)), 'NFHL Spatial Check'] = 'Fail'
            print(nfhl_compare)
        df.to_csv(report_file, sep='\t', index=False)
        with open(report_file, "a") as report:
            report.write(nfhl_compare)
        return

class MappingValueCheck(object):
    
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "3. Mapping Value Check"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(displayName="Flood Risk Database",name="Flood_Risk_Database",datatype="DEWorkspace",parameterType="Required",direction="Input")
        param1 = arcpy.Parameter(displayName="QAQC Report Folder",name="QAQC_Report_Folder",datatype="DEFolder",parameterType="Required",direction="Input")
        param2 = arcpy.Parameter(displayName="Test Points",name="Test_Points",datatype="DEFeatureClass",parameterType="Derived",direction="Output")
        param2.parameterDependencies = [param0.name]
        params = [param0, param1, param2]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        if not str(parameters[0].value).endswith('.gdb'):
            parameters[0].setErrorMessage('Not a file geodatabase')
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        in_gdb = parameters[0].valueAsText
        out_folder = parameters[1].valueAsText
        
        report_name = 'QAQC_Report_' + os.path.basename(in_gdb).split('.')[0][8:] + '.txt'
        report_file = os.path.join(out_folder, report_name)
        fema_portal = r"https://fema.maps.arcgis.com/"
        item_id = 'b25c03c4dee0491faba5d479a457ed03'  
        arcpy.env.workspace = in_gdb
        scratch_gdb = arcpy.env.scratchWorkspace
        # Environment Settings
        arcpy.env.overwriteOutput = True
        arcpy.env.addOutputsToMap = False
        feature_datasets = arcpy.ListDatasets({}, "Feature")
        features = [(ds, fc) for ds in feature_datasets for fc in arcpy.ListFeatureClasses(feature_dataset = ds)]        
        raster_datasets = arcpy.ListDatasets({}, "Raster")
        rasters = [raster for raster in raster_datasets]
        #regex to account for errors in BFE_2D naming
        r = re.compile("BFE", re.IGNORECASE)
        bfe_match = list(filter(r.match, [i[1] for i in features]))
        if bfe_match and 'BLEWSE01PCT' in [i.replace('_', '') for i in rasters]:
            arcpy.SetProgressorLabel('Checking if BFE_2D is in the database.....')
            arcpy.AddMessage('Checking if BFE_2D is in the database.....')
            with open(report_file, "a") as report:
                report.write('\n-----------------------------------------------\nTool 3 - Results:\n-----------------------------------------------')
            test_points = self.bfe_2d_check(bfe_match[0],'BLEWSE01PCT',report_file,in_gdb,features,scratch_gdb, rasters)            
            #arcpy.SetParameter(2, test_points)
            #outsym = f"JSONRENDERER={outsym}"
            #outsym = f'JSONCIMDEF={outsym}'
            outsym = self.get_symbology(fema_portal,item_id,report_file)
            parameters[2].value = test_points
            parameters[2].symbology = outsym
            #arcpy.SetParameterSymbology(2, outsym)
            #arcpy.SetParameterAsText(3, report_file)            
            arcpy.AddMessage('BFE_2D mapping value check is complete.....')
            arcpy.AddMessage(f'Report file path: {report_file}')
        with arcpy.EnvManager(workspace = arcpy.env.scratchWorkspace):
                to_delete = arcpy.ListFeatureClasses("*X")
                for fc in to_delete:
                        arcpy.management.Delete(os.path.join(arcpy.env.scratchWorkspace, fc))
        if not bfe_match: 
            arcpy.AddMessage('BFE_2D is missing from the database')
        if 'BLEWSE01PCT' not in [i.replace('_', '') for i in rasters]:
            arcpy.AddMessage('BLE_WSE_01PCT is missing from the database')
        return
    
    def get_grid_index(self, grid_name, rasters):
        grid_index = [i.replace('_', '') for i in rasters].index(grid_name) if grid_name in [i.replace('_', '') for i in rasters] else -1
        return grid_index

    def create_gdb(self,data_dir,report_file):
        gdb_name = os.path.basename(report_file)[:-4]
        if os.path.isdir(os.path.join(data_dir, gdb_name+'.gdb')):        
            gdb_path = os.path.join(data_dir, gdb_name+'.gdb')
        else:        
            gdb_name = os.path.basename(report_file)[:-4]
            gdb_path = arcpy.management.CreateFileGDB(data_dir, gdb_name)
            gdb_path = gdb_path.getOutput(0)
        return gdb_path

    def get_symbology(self,portal,item_id,report_file):
        try:     
            #downloads_path = str(Path.home() / "Downloads")    # path to downloads folder
            data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
            file_name = os.path.join(data_dir, 'Symbology', 'BFE_2D_TestPoints.lyrx')
            if os.path.isfile(file_name):
                downloaded_item = file_name
            else:
                gis = GIS(portal)
                tool_data = gis.content.get(item_id)
                zipped_tool_data = tool_data.download(data_dir)    # download the data item
                z = zipfile.ZipFile(zipped_tool_data)
                z.extractall(data_dir)
                downloaded_item = os.path.join(data_dir, 'Symbology', 'BFE_2D_TestPoints.lyrx')     
        except Exception as e:
            print(f'Error unzipping file: {e}')
        return downloaded_item
    

    def bfe_2d_check(self,test_feature,wse_01pct,report_file,in_gdb,features,scratch_gdb, rasters):
        data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
        if os.path.isdir(data_dir):
            save_path = self.create_gdb(data_dir,report_file)
        else: save_path = self.create_gdb(os.makedirs(data_dir),report_file)
        test_index = [i[1] for i in features].index(test_feature)
        test_feature = os.path.join(in_gdb, features[test_index][0], features[test_index][1])
        wse_grid = os.path.join(in_gdb,  rasters[self.get_grid_index(wse_01pct, rasters)])
        #wse_grid = os.path.join(in_gdb, wse_01pct)
        arcpy.SetProgressorLabel('Testing BFE_2D......')
        arcpy.AddMessage('Testing BFE_2D......')
        arcpy.management.CalculateField(test_feature, "LEN_FT", '!SHAPE!.getLength("GEODESIC", "FEET")', "PYTHON3", '', "FLOAT", "NO_ENFORCE_DOMAINS")
        arcpy.management.AddFields(test_feature, "X DOUBLE;Y DOUBLE;X_FIRST DOUBLE;Y_FIRST DOUBLE;X_LAST DOUBLE;Y_LAST DOUBLE")
        arcpy.management.CalculateFields(test_feature, "PYTHON3", "X !SHAPE!.labelPoint.X;Y !SHAPE!.labelPoint.Y", '', "NO_ENFORCE_DOMAINS")
        bfe_over_200 = arcpy.management.MakeFeatureLayer(test_feature, "BFE_2D_Layer>200FT", "LEN_FT > 200")
        arcpy.management.CalculateFields(bfe_over_200.getOutput(0), "PYTHON3", "X_FIRST '!SHAPE!.positionAlongLine(0.01, True).firstPoint.X';Y_FIRST '!SHAPE!.positionAlongLine(0.01, True).firstPoint.Y'", '', "NO_ENFORCE_DOMAINS")
        arcpy.management.CalculateFields(bfe_over_200.getOutput(0), "PYTHON3", "X_LAST '!SHAPE!.positionAlongLine(0.99, True).lastPoint.X';Y_LAST '!SHAPE!.positionAlongLine(0.99, True).lastPoint.Y'", '', "NO_ENFORCE_DOMAINS")    
        sr = arcpy.Describe(test_feature).spatialReference
        sr_project = arcpy.Raster(wse_grid).spatialReference
        transform = arcpy.ListTransformations(sr, sr_project)
        bfe_points = arcpy.management.XYTableToPoint(test_feature, os.path.join(scratch_gdb, "BFE_2D_TestPointsX"), "X", "Y", None, sr)
        bfe_points_first = arcpy.management.XYTableToPoint(test_feature, os.path.join(scratch_gdb,"BFE_2D_PointFirstX"), "X_FIRST", "Y_FIRST", None, sr)
        bfe_points_last = arcpy.management.XYTableToPoint(test_feature, os.path.join(scratch_gdb,"BFE_2D_PointLastX"), "X_LAST", "Y_LAST", None, sr)
        arcpy.management.Append([bfe_points_first, bfe_points_last], bfe_points)
        arcpy.management.DeleteField(test_feature, "X;Y;LEN_FT;X_FIRST;Y_FIRST;X_LAST;Y_LAST", "DELETE_FIELDS")
        try:
            bfe_points = arcpy.management.Project(bfe_points, os.path.join(save_path,"BFE_2D_TestPoints"), sr_project, transform[0], sr, "NO_PRESERVE_SHAPE", None, "NO_VERTICAL")
        except:
            bfe_points = arcpy.management.Project(bfe_points, os.path.join(save_path,"BFE_2D_TestPoints"), sr_project, None, sr, "NO_PRESERVE_SHAPE", None, "NO_VERTICAL")
        arcpy.sa.ExtractMultiValuesToPoints(bfe_points, f"{wse_grid} BFE_BASE", "NONE")
        #add difference column
        arcpy.management.CalculateField(bfe_points, "Difference", "!BLELEV1PCT! - !BFE_BASE!", "PYTHON3", '', "FLOAT", "NO_ENFORCE_DOMAINS")
        arr = arcpy.da.FeatureClassToNumPyArray(bfe_points, ['Difference'])
        bfe_compare = arr['Difference']
        test_points = np.round(bfe_compare[~np.isnan(bfe_compare)],0)
        max_diff = test_points.max()
        bfe_plus = test_points[test_points > 0].size
        bfe_minus = test_points[test_points < 0].size
        less_one = test_points[abs(test_points) < 1].size
        more_one = test_points[abs(test_points) >= 1].size 
        bfe_compare = f'Total BFE points tested: {test_points.size:,}\nBFE points above WSE grid values: {bfe_plus:,}\nBFE points below WSE grid values: {bfe_minus:,}\n{((bfe_plus+bfe_minus)/test_points.size):.1%} of points failed\nMaximum difference: {round(max_diff, 1)} ft\nNumber of points failed within +/- 1 ft: {less_one:,}\nNumber of points failed greater +/- 1 ft: {more_one:,}'
        df = pd.read_csv(report_file, '\t')
        df.loc[df["Item Name"] == os.path.basename(test_feature), 'Mapping Value Check'] = f'Failed by {((bfe_plus+bfe_minus)/test_points.size):.1%}'
        df.to_csv(report_file, sep='\t', index=False)
        with open(report_file, "a") as report:
                report.write(bfe_compare)
        arcpy.AddMessage(f'Total BFE points tested: {test_points.size:,}')
        arcpy.AddMessage(f'BFE points below WSE grid values: {bfe_plus:,}')
        arcpy.AddMessage(f'BFE points above WSE grid values: {bfe_minus:,}')
        arcpy.AddMessage(f'{((bfe_plus+bfe_minus)/test_points.size):.1%} of points failed. See Supplemental Data feature BFE_2D_TestPoints')
        return bfe_points
    
class WaterbodiesCheck(object):
    
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "4. Waterbodies Check"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(displayName="Flood Risk Database",name="Flood_Risk_Database",datatype="DEWorkspace",parameterType="Required",direction="Input")
        param1 = arcpy.Parameter(displayName="QAQC Report Folder",name="QAQC_Report_Folder",datatype="DEFolder",parameterType="Required",direction="Input")
        param2 = arcpy.Parameter(displayName="Missing Waterbodies",name="Missing_Wtr",datatype="DEFeatureClass",parameterType="Derived",direction="Output")
        param3 = arcpy.Parameter(displayName="Extra Waterboides",name="Extra_Wtr",datatype="DEFeatureClass",parameterType="Derived",direction="Output")
        param2.parameterDependencies = [param0.name]
        param3.parameterDependencies = [param0.name]
        params = [param0, param1, param2, param3]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        if not str(parameters[0].value).endswith('.gdb'):
            parameters[0].setErrorMessage('Not a file geodatabase')
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        in_gdb = parameters[0].valueAsText
        out_folder = parameters[1].valueAsText
        
        report_name = 'QAQC_Report_' + os.path.basename(in_gdb).split('.')[0][8:] + '.txt'
        report_file = os.path.join(out_folder, report_name)
        fema_portal = r"https://fema.maps.arcgis.com/"
        item_id = 'b25c03c4dee0491faba5d479a457ed03'  
        arcpy.env.workspace = in_gdb
        scratch_gdb = arcpy.env.scratchWorkspace
        # Environment Settings
        arcpy.env.overwriteOutput = True
        arcpy.env.addOutputsToMap = False
        feature_datasets = arcpy.ListDatasets({}, "Feature")
        features = [(ds, fc) for ds in feature_datasets for fc in arcpy.ListFeatureClasses(feature_dataset = ds)]
        if 'WTR_AR' in [i[1] for i in features]:
            print('Located WTR_AR in the database')
            with open(report_file, "a") as report:
                report.write('\n-----------------------------------------------\nTool 4 - Results:\n-----------------------------------------------')
            missing = self.nhd_compare('WTR_AR',report_file,features,in_gdb,fema_portal,item_id,scratch_gdb)
            #arcpy.SetParameter(2, missing[0])#missing waterbodies
            #arcpy.SetParameter(3, missing[1])#extra waterbodies
            outsym = self.get_symbology(fema_portal, item_id, report_file)
            parameters[2].value = missing[0]
            parameters[2].symbology = outsym
            parameters[3].value = missing[1]
            parameters[3].symbology = outsym
            #arcpy.management.ApplySymbologyFromLayer(missing[0],outsym)
            #arcpy.management.ApplySymbologyFromLayer(missing[1],outsym)
            #arcpy.SetParameterSymbology(2, outsym)
            #arcpy.SetParameterSymbology(3, outsym)
            #arcpy.SetParameterAsText(4, report_file)
            arcpy.AddMessage(f'Report file path: {report_file}')
        with arcpy.EnvManager(workspace = arcpy.env.scratchWorkspace):
            to_delete = arcpy.ListFeatureClasses("*X")
            for fc in to_delete:
                    arcpy.management.Delete(os.path.join(arcpy.env.scratchWorkspace, fc))
        if 'WTR_AR' not in [i[1] for i in features]: 
            arcpy.AddMessage('BFE_2D is missing from the database')
        return

    def create_gdb(self,data_dir,report_file):
        gdb_name = os.path.basename(report_file)[:-4]
        if os.path.isdir(os.path.join(data_dir, gdb_name+'.gdb')):            
            gdb_path = os.path.join(data_dir, gdb_name+'.gdb')
        else:            
            gdb_name = os.path.basename(report_file)[:-4]
            gdb_path = arcpy.management.CreateFileGDB(data_dir, gdb_name)
            gdb_path = gdb_path.getOutput(0)
        return gdb_path

    def unzip_data(self,portal,item_id,report_file):
        arcpy.SetProgressorLabel('Getting NHD data...')
        arcpy.AddMessage('Getting NHD data...')
        try:     
            #downloads_path = str(Path.home() / "Downloads")    # path to downloads folder
            data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
            if os.path.isdir(data_dir):
                downloaded_gdb = os.path.join(data_dir, 'BLE-QAQC-Tools-Data.gdb')
            else:
                gis = GIS(portal)
                tool_data = gis.content.get(item_id)
                os.makedirs(data_dir)
                zipped_tool_data = tool_data.download(data_dir)    # download the data item
                z = zipfile.ZipFile(zipped_tool_data)
                z.extractall(data_dir)
                downloaded_gdb = os.path.join(data_dir, 'BLE-QAQC-Tools-Data.gdb')       
        except Exception as e:
            arcpy.AddMessage(f'Error getting data: {e}')
        return downloaded_gdb

    def get_symbology(self,portal,item_id,report_file):
        try:     
            #downloads_path = str(Path.home() / "Downloads")    # path to downloads folder
            data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
            file_name = os.path.join(data_dir, 'Symbology', 'Waterbodies_Symbology.lyrx')
            if os.path.isfile(file_name) :
                downloaded_item = file_name
            else:
                gis = GIS(portal)
                tool_data = gis.content.get(item_id)
                zipped_tool_data = tool_data.download(data_dir)    # download the data item
                z = zipfile.ZipFile(zipped_tool_data)
                z.extractall(data_dir)
                downloaded_item = os.path.join(data_dir, 'Symbology', 'Waterbodies_Symbology.lyrx')     
        except Exception as e:
            print(f'Error unzipping file: {e}')
        return downloaded_item


    def nhd_compare(self,test_feature,report_file,features,in_gdb,fema_portal,item_id,scratch_gdb):
        data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
        save_path = self.create_gdb(data_dir,report_file)
        try: 
            huc8_index = [i[1] for i in features].index('S_HUC_Ar')
            huc8_feature = os.path.join(in_gdb, features[huc8_index][0], features[huc8_index][1])
        except:
            huc8_feature = os.path.join(self.unzip_data(fema_portal,item_id,report_file), 'WBDHU8')
            huc8_layer = arcpy.MakeFeatureLayer_management(huc8_feature, "WBDHU8")
            huc8_layer = arcpy.management.SelectLayerByLocation(huc8_layer.getOutput(0), "INTERSECT", test_feature, "-1 Miles", "NEW_SELECTION", "NOT_INVERT")
            test_feature_sr = arcpy.Describe(test_feature).spatialReference
            with arcpy.EnvManager(outputCoordinateSystem=test_feature_sr):
                huc8_feature = arcpy.conversion.FeatureClassToFeatureClass(huc8_layer, scratch_gdb, "HUC8_BaseFeatureX")
        test_index = [i[1] for i in features].index(test_feature)
        test_feature = os.path.join(in_gdb, features[test_index][0], features[test_index][1])
        huc_sr = arcpy.Describe(huc8_feature).spatialReference
        
        with arcpy.EnvManager(workspace = arcpy.env.scratchWorkspace):
            if arcpy.Exists(os.path.join(scratch_gdb, "NHD_ProjectX")):
                nhd_project = os.path.join(scratch_gdb, "NHD_ProjectX")
            if arcpy.Exists(os.path.join(scratch_gdb, "NHD_ClipedX")):
                nhd_clip = os.path.join(scratch_gdb, "NHD_ClipedX")
            else:
                nhd_fl = os.path.join(self.unzip_data(fema_portal,item_id,report_file), 'NHD')
                nhd_project = arcpy.management.Project(nhd_fl, os.path.join(scratch_gdb, "NHD_ProjectX"), huc_sr, None, None, "NO_PRESERVE_SHAPE", None, "NO_VERTICAL")
                nhd_clip = arcpy.analysis.PairwiseClip(nhd_project, huc8_feature, os.path.join(scratch_gdb, "NHD_ClipedX"), None)

        wtr_layer = arcpy.MakeFeatureLayer_management(test_feature, os.path.basename(test_feature))
        nhd_layer = arcpy.MakeFeatureLayer_management(nhd_clip, "NHD_Clipped")

        compare_layer = arcpy.management.SelectLayerByLocation(nhd_layer.getOutput(0), "INTERSECT", wtr_layer.getOutput(0), None, "NEW_SELECTION", "INVERT")
        nhdX = arcpy.conversion.FeatureClassToFeatureClass(compare_layer.getOutput(0), scratch_gdb, "Missing_WaterbodiesX")
        nhdX_layer = arcpy.MakeFeatureLayer_management(nhdX, "Missing_Waterbodies")
        nhdX_count = len(compare_layer.getOutput(0).getSelectionSet())
        arcpy.management.CalculateGeometryAttributes(nhdX_layer.getOutput(0), "AreaSqFt AREA_GEODESIC", '', '', None, "SAME_AS_INPUT")
        nhdX_max = arcpy.management.SelectLayerByAttribute(nhdX_layer.getOutput(0), "NEW_SELECTION", "AreaSqFt = (SELECT MAX(AreaSqFt) FROM Missing_WaterbodiesX)", None)
        arr = arcpy.da.FeatureClassToNumPyArray(nhdX_max, "AreaSqFt")
        nhd_max_ft = f'{round(arr["AreaSqFt"][0]):,}' + ' sq.ft'
        nhd_max_acres = f'{round(arr["AreaSqFt"][0]/43560):,}' + ' acres'
        nhd_compare = f'There are {nhdX_count:,} missing WTR_AR polygons with the max area of {nhd_max_ft} or {nhd_max_acres}. See Supplemental Data feature Missing_Waterbodies'
        wtr_layer = arcpy.MakeFeatureLayer_management(test_feature, os.path.basename(test_feature))
        nhd_layer = arcpy.MakeFeatureLayer_management(nhd_clip, "NHD_Clipped")
        compare_layer = arcpy.management.SelectLayerByLocation(wtr_layer.getOutput(0), "INTERSECT", nhd_layer.getOutput(0), None, "NEW_SELECTION", "INVERT")
        wtrX = arcpy.conversion.FeatureClassToFeatureClass(compare_layer.getOutput(0), scratch_gdb, "Extra_WaterbodiesX")
        arcpy.management.CalculateGeometryAttributes(wtrX, "AreaSqFt AREA_GEODESIC", '', '', None, "SAME_AS_INPUT")
        
        wtrX_count = len(compare_layer.getOutput(0).getSelectionSet())
        wtr_compare = f'\nThere are {wtrX_count} extra WTR_AR polygons. See Supplemental Data feature Extra_Waterbodies'
        print(wtr_compare)
        
        df = pd.read_csv(report_file, '\t')
        if nhd_compare and wtr_compare == 0:
            
            df.loc[df["Item Name"] == os.path.basename(test_feature), 'Waterbodies Check'] = 'Pass'
            df.to_csv(report_file, sep='\t', index=False)
            with open(report_file, "a") as report:
                report.write(nhd_compare)
                report.write(wtr_compare)        
        else:
            df.loc[df["Item Name"] == os.path.basename(test_feature), 'Waterbodies Check'] = 'Fail'
            df.to_csv(report_file, sep='\t', index=False)
            with open(report_file, "a") as report:
                report.write(nhd_compare)
                report.write(wtr_compare)
            nhdX = arcpy.conversion.FeatureClassToFeatureClass(nhdX, save_path, "Missing_Waterbodies")
            wtrX = arcpy.conversion.FeatureClassToFeatureClass(wtrX, save_path, "Extra_Waterbodies")
            return [nhdX, wtrX]

class FloodHazardAreaCheck(object):
    
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "5. Flood Hazard Area Check"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(displayName="Flood Risk Database",name="Flood_Risk_Database",datatype="Workspace",parameterType="Required",direction="Input")
        param1 = arcpy.Parameter(displayName="QAQC Report Folder",name="QAQC_Report_Folder",datatype="DEFolder",parameterType="Required",direction="Input")
        params = [param0, param1]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""

        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        if not str(parameters[0].value).endswith('.gdb'):
            parameters[0].setErrorMessage('Not a file geodatabase')
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        in_gdb = parameters[0].valueAsText
        out_folder = parameters[1].valueAsText
        
        report_name = 'QAQC_Report_' + os.path.basename(in_gdb).split('.')[0][8:] + '.txt'
        report_file = os.path.join(out_folder, report_name)
        arcpy.env.workspace = in_gdb
        scratch_gdb = arcpy.env.scratchWorkspace
        # Environment Settings
        arcpy.env.overwriteOutput = True
        arcpy.env.addOutputsToMap = False
        feature_datasets = arcpy.ListDatasets({}, "Feature")
        features = [(ds, fc) for ds in feature_datasets for fc in arcpy.ListFeatureClasses(feature_dataset = ds)]
        raster_datasets = arcpy.ListDatasets({}, "Raster")
        rasters = [raster for raster in raster_datasets]
        with open(report_file, "a") as report:
                report.write('\n-----------------------------------------------\nTool 5 - Results:\n-----------------------------------------------')
        if ('BLEWSE01PCT' or 'BLEWSE02PCT') not in [i.replace('_', '') for i in rasters]: 
            arcpy.AddMessage('One or more WSE grids are missing from the database')
        if ('BLEDEP01PCT' or 'BLEDEP02PCT') not in [i.replace('_', '') for i in rasters]:
            arcpy.AddMessage('One or more depth grids are missing from the database')
            
        #extent comparison
        if 'BLEDEP01PCT' and 'BLEDEP02PCT' in [i.replace('_', '') for i in rasters]:
            arcpy.SetProgressorLabel('Checking if depth grids are in the database.....')
            arcpy.AddMessage('Checking if depth grids are in the database.....')
            grids = ['BLEDEP01PCT', 'BLEDEP02PCT']
            depth_check = self.grid_containment_check(grids, in_gdb, report_file, rasters)
            #depth_check.save(os.path.join(scratch_gdb, 'Depth_Grid_Compare'))

        if 'BLEWSE01PCT' and 'BLEWSE02PCT' in [i.replace('_', '') for i in rasters]:
            arcpy.SetProgressorLabel('Checking if WSE grids are in the database.....')
            arcpy.AddMessage('Checking if WSE grids are in the database.....')
            grids = ['BLEWSE01PCT', 'BLEWSE02PCT']
            wse_check = self.grid_containment_check(grids, in_gdb, report_file, rasters)
            #wse_check.save(os.path.join(scratch_gdb, 'WSE_Grid_Compare'))        
            
        #grid value check for positive values and correctly labeled datasets and snapping check
        if 'BLEWSE01PCT' and 'BLEDEP01PCT' in [i.replace('_', '') for i in rasters]:
            grids = ['BLEWSE01PCT', 'BLEDEP01PCT']
            value_check = self.grid_value_check(grids, in_gdb, report_file, rasters)
            polys_100 = self.snapping_check(grids, in_gdb, report_file, scratch_gdb, rasters)
        if 'BLEWSE02PCT' and 'BLEDEP02PCT' in [i.replace('_', '') for i in rasters]:
            grids = ['BLEWSE02PCT','BLEDEP02PCT']
            value_check = self.grid_value_check(grids, in_gdb, report_file, rasters)
            polys_500 = self.snapping_check(grids, in_gdb, report_file, scratch_gdb, rasters)

        feature_datasets = arcpy.ListDatasets({}, "Feature")
        features = [(ds, fc) for ds in feature_datasets for fc in arcpy.ListFeatureClasses(feature_dataset = ds)]
        fld_index = [i[1] for i in features].index('FLD_HAZ_AR')
        tenpct_index = [i[1] for i in features].index('TENPCT_FP')
        tenpct_feature = os.path.join(in_gdb, features[tenpct_index][0], features[tenpct_index][1])
        fld_feature = os.path.join(in_gdb, features[fld_index][0], features[fld_index][1])        
            
        self.tenpct_extent_check(tenpct_feature, fld_feature, report_file)

        fld_haz_layer = arcpy.MakeFeatureLayer_management(fld_feature, "FLD_HAZ_AR")
        arcpy.SetProgressorLabel('Performing grid vs FLD_HAZ_AR check.....')
        arcpy.AddMessage('Performing grid vs FLD_HAZ_AR check.....')
        #polys_100 and 500 might not be defined if the grids are missing from the database
        missing_polys_100 = self.grid_vs_poly(polys_100[0], fld_haz_layer, 'A', report_file)
        if missing_polys_100[0] > 0:
            with open(report_file, "a") as report:
                report.write(f'\nThere are {missing_polys_100[0]:,} missing features in the 100-yr FLD_HAZ_AR with the average area of {round(missing_polys_100[2], 5)} sq.mi and max area of {missing_polys_100[3]} sq.mi. See Supplemental Data feature {missing_polys_100[1]}')
        
            arcpy.AddMessage(f'There are {missing_polys_100[0]:,} missing features in the 100-yr FLD_HAZ_AR')
            
        fld_haz_layer = arcpy.MakeFeatureLayer_management(fld_feature, "FLD_HAZ_AR")   
        missing_polys_500 = self.grid_vs_poly(polys_500[0], fld_haz_layer, None, report_file)
        if missing_polys_500[0] > 0:
            with open(report_file, "a") as report:
                report.write(f'\nThere are {missing_polys_500[0]:,} missing features in the 500-yr FLD_HAZ_AR with the average area of {round(missing_polys_500[2], 5)} sq.mi and max area of {missing_polys_500[3]} sq.mi. See Supplemental Data feature {missing_polys_500[1]}')
                
            arcpy.AddMessage(f'There are {missing_polys_500[0]}:, missing features the 500-yr FLD_HAZ_AR')
            
        if 'FLD_HAZ_AR' and 'WTR_LN' in [i[1] for i in features]:
            self.wtr_ln_check('WTR_LN', fld_feature, report_file, in_gdb, features)
        arcpy.AddMessage(f'Report file path: {report_file}')       
        with arcpy.EnvManager(workspace = arcpy.env.scratchWorkspace):
            to_delete = arcpy.ListFeatureClasses("*X")
            for fc in to_delete:
                arcpy.management.Delete(os.path.join(arcpy.env.scratchWorkspace, fc))
        return
    
    def get_grid_index(self, grid_name, rasters):
        grid_index = [i.replace('_', '') for i in rasters].index(grid_name) if grid_name in [i.replace('_', '') for i in rasters] else -1
        return grid_index

    def create_gdb(self, data_dir, report_file):
        gdb_name = os.path.basename(report_file)[:-4]
        if os.path.isdir(os.path.join(data_dir, gdb_name+'.gdb')):            
            gdb_path = os.path.join(data_dir, gdb_name+'.gdb')
        else:            
            gdb_name = os.path.basename(report_file)[:-4]
            gdb_path = arcpy.management.CreateFileGDB(data_dir, gdb_name)
            gdb_path = gdb_path.getOutput(0)
        return gdb_path

    def grid_containment_check(self, grids, in_gdb, report_file, rasters):
        data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
        save_path = self.create_gdb(data_dir, report_file)
        arcpy.SetProgressorLabel('Performing grid containment check.....')
        arcpy.AddMessage('Performing grid containment check.....')
        grids_path = [os.path.join(in_gdb,  rasters[self.get_grid_index(grids[0], rasters)]), os.path.join(in_gdb, rasters[self.get_grid_index(grids[1], rasters)])]
        with arcpy.EnvManager(snapRaster=grids_path[1]):
            grid_check = arcpy.sa.SetNull(~(arcpy.sa.IsNull(grids_path[1])),  grids_path[0])
        if not grid_check.mean:
            extent_compare = f'\n{grids[0]} does NOT extend outside of {grids[1]}'
            arcpy.AddMessage(f'{grids[0]} does NOT extend outside of {grids[1]}.....')
        elif grid_check.mean:
            con_raster = arcpy.sa.Con(grid_check, 0, None, '')
            name = {'BLEDEP01PCT': 'Depth', 'BLEWSE01PCT': 'WSE'}
            arcpy.conversion.RasterToPolygon(con_raster, os.path.join(save_path, f'{name[grids[0]]}_Grid_Containment_Check'), "NO_SIMPLIFY", "Value", "SINGLE_OUTER_PART", None)
            extent_compare = f'\n{grids[0]} extends outside of {grids[1]}. See Supplemental Data feature {name[grids[0]]}_Grid_Containment_Check.'
            arcpy.AddMessage(f'{grids[0]} extends outside of {grids[1]}.....')
        with open(report_file, "a") as report:
                    report.write(extent_compare)
        return grid_check

    def grid_value_check(self, grids, in_gdb, report_file, rasters):

        arcpy.SetProgressorLabel('Performing grid value check.....')
        arcpy.AddMessage('Performing grid value check.....')
        grids_path = [os.path.join(in_gdb,  rasters[self.get_grid_index(grids[0], rasters)]), os.path.join(in_gdb, rasters[self.get_grid_index(grids[1], rasters)])]
        with arcpy.EnvManager(snapRaster=grids_path[1]):
            value_check = arcpy.sa.Minus(grids_path[0], grids_path[1])
    #     if value_check.minimum > 0:
    #         value_compare = '\nNo negative values for 1% grids'
        if value_check.minimum < 0:
            value_compare = f'\n{grids[1]} values greater than {grids[0]} values. Check for correct naming.'
            arcpy.AddMessage(value_compare)
            with open(report_file, "a") as report:
                report.write(value_compare)
        arcpy.management.Delete(value_check)
        #return value_compare

    def snapping_check(self, grids, in_gdb, report_file, scratch_gdb, rasters):
        data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
        save_path = self.create_gdb(data_dir, report_file)
        arcpy.SetProgressorLabel('Performing grid extent check.....')
        arcpy.AddMessage('Performing grid extent check.....')
        grids_path = [os.path.join(in_gdb,  rasters[self.get_grid_index(grids[0], rasters)]), os.path.join(in_gdb, rasters[self.get_grid_index(grids[1], rasters)])]
        feature_compare = []
        for path, grid_name in zip(grids_path, grids):
            with arcpy.EnvManager(snapRaster=path):
                con_raster = arcpy.sa.Con(path, 0, None, '')
            poly = arcpy.conversion.RasterToPolygon(con_raster, os.path.join(scratch_gdb, grid_name+'_Poly'), "NO_SIMPLIFY", "Value", "SINGLE_OUTER_PART", None)
            feature_compare.append(poly)
        snap_compare = arcpy.management.FeatureCompare(feature_compare[0], feature_compare[1], "OBJECTID", "GEOMETRY_ONLY", "IGNORE_M;IGNORE_Z;IGNORE_POINTID;IGNORE_EXTENSION_PROPERTIES;IGNORE_SUBTYPES;IGNORE_RELATIONSHIPCLASSES;IGNORE_REPRESENTATIONCLASSES;IGNORE_FIELDALIAS", "0.003280833333 Feet", 0.001, 0.001, None, None, "CONTINUE_COMPARE", None)
        #messages = snap_compare.getMessages()
        
        if 'Geometries are different for ObjectID' in snap_compare.getMessages(1):
            for feature, name in zip(feature_compare, grids):
                arcpy.conversion.FeatureClassToFeatureClass(feature, save_path, name+'_Poly')
            diff_features = snap_compare.getMessages(1).replace('FeatureClass: ', '')
            snap_compare = f'\n{grids[0]} and {grids[1]} extents are different. See Supplemental Data features {grids[0]}_Poly and {grids[1]}_Poly\n{diff_features}'
            arcpy.AddMessage(snap_compare)
            with open(report_file, "a") as report:
                report.write(snap_compare)
        elif 'Geometries are different' in snap_compare.getMessages():
            print(f'\n{grids[0]} and {grids[1]} extents are different. Check snapping.')
            snap_compare = f'\n{grids[0]} and {grids[1]} extents are different. Check snapping.'
            arcpy.AddMessage(snap_compare)
            with open(report_file, "a") as report:
                report.write(snap_compare) 
        return feature_compare

    def grid_vs_poly(self, grid, fld_haz_layer, fld_zone, report_file):
        data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
        save_path = self.create_gdb(data_dir, report_file)
        if fld_zone:
            fld_haz_layer.getOutput(0).definitionQuery = f"FLD_ZONE = '{fld_zone}'"
        grid_layer = arcpy.MakeFeatureLayer_management(grid, "Grid_Layer")
        missing_polys = arcpy.management.SelectLayerByLocation(grid_layer, "INTERSECT", fld_haz_layer, None, "NEW_SELECTION", "INVERT")
        name = {'A': '01PCT', None: '0_2PCT'}
        missing_count = len(missing_polys.getOutput(0).getSelectionSet())
        if missing_count > 0:
            missing_polys = arcpy.conversion.FeatureClassToFeatureClass(missing_polys.getOutput(0), save_path, f'Missing_Features_{name[fld_zone]}')
            missing_name = f'Missing_Features_{name[fld_zone]}'
            arcpy.management.CalculateGeometryAttributes(missing_polys, "AreaSqMiles AREA", '', "SQUARE_MILES_US", None, "SAME_AS_INPUT")
            arr = arcpy.da.FeatureClassToNumPyArray(missing_polys, "AreaSqMiles")
            mean_area = arr["AreaSqMiles"].round(5).mean()
            max_area = arr["AreaSqMiles"].round(5).max()

            return [missing_count, missing_name, mean_area, max_area]
        else: return [0]

    def tenpct_extent_check(self, tenpct, fld_haz_ar, report_file):
        arcpy.SetProgressorLabel('Performing TENPCT_FP extent check.....')
        arcpy.AddMessage('Performing TENPCT_FP extent check.....')
        data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
        save_path = self.create_gdb(data_dir, report_file)
        tenpct_layer = arcpy.MakeFeatureLayer_management(tenpct, "TENPCT_Layer")
        fld_haz_layer = arcpy.MakeFeatureLayer_management(fld_haz_ar, "FLD_HAZ_AR_Layer")
        fld_zone = 'A'
        fld_haz_layer.getOutput(0).definitionQuery = f"FLD_ZONE = '{fld_zone}'"
        tenpct_extent= arcpy.management.SelectLayerByLocation(tenpct_layer.getOutput(0), "WITHIN", fld_haz_layer.getOutput(0), None, "NEW_SELECTION", "INVERT")
        if len(tenpct_extent.getOutput(0).getSelectionSet()) > 0:
            tenpct_message = '\nTENPCT_FP extends outside of 100-yr FLD_HAZ_AR. See Supplemental Data feature TENPCT_FP_Containment_Check.'
            #arcpy.conversion.FeatureClassToFeatureClass(tenpct_extent, save_path, 'TENPCT_FP_Containment_Check')
            arcpy.analysis.PairwiseErase(tenpct_layer.getOutput(0), fld_haz_layer.getOutput(0), os.path.join(save_path, 'TENPCT_FP_Containment_Check'))
        else:
            tenpct_message = '\nTENPCT_FP does NOT extend outside of 100-yr FLD_HAZ_AR'
        with open(report_file, "a") as report:
                report.write(tenpct_message)

    def wtr_ln_check(self, wtr_ln, fld_haz_ar, report_file, in_gdb, features):
        data_dir = os.path.join(os.path.dirname(report_file), 'Supplemental Data')
        save_path = self.create_gdb(data_dir, report_file)
        wtr_index = [i[1] for i in features].index(wtr_ln)
        wtr_feature = os.path.join(in_gdb, features[wtr_index][0], features[wtr_index][1])
        wtr_check = arcpy.analysis.PairwiseErase(wtr_feature, fld_haz_ar, os.path.join(save_path, "Centerline_Containment"), None)
        arcpy.management.AddFields(wtr_check, "Comment TEXT # 255 # #;Response TEXT # 255 # #")        
        wtr_count = arcpy.management.GetCount(wtr_check).getOutput(0)
        if int(wtr_count) > 0:
            wtr_message = f'\n{int(wtr_count):,} WTR_LN segments identified outside of FLD_HAZ_AR. See Supplemental Data feature Centerline_Containment.'
            with open(report_file, "a") as report:
                report.write(wtr_message)
