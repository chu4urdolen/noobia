#include "camera_common.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define MAX_TENSOR_VALUES 4096
#define MAX_MODELS 16

typedef enum { MODEL_OBJECT, MODEL_POSE } model_kind;
typedef struct { const char *id, *description, *config_name, *network; model_kind kind; double coordinate_scale; } model_spec;
typedef struct { const model_spec *model; char image[PATH_MAX], metadata[PATH_MAX], results[PATH_MAX]; } model_run;

static const model_spec models[] = {
    {"object0", "MobileNet SSD: broad, balanced COCO object detection", "imx500_mobilenet_ssd.json", "imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk", MODEL_OBJECT, 1.0},
    {"object1", "EfficientDet Lite0: stronger general object detection", "imx500_mobilenet_ssd.json", "imx500_network_efficientdet_lite0_pp.rpk", MODEL_OBJECT, 320.0},
    {"object2", "NanoDet Plus: compact general object detection", "imx500_mobilenet_ssd.json", "imx500_network_nanodet_plus_416x416_pp.rpk", MODEL_OBJECT, 1.0},
    {"pose0", "PoseNet: human pose and skeleton overlay", "imx500_posenet.json", "imx500_network_posenet.rpk", MODEL_POSE, 1.0}
};

static const char *classes[100] = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light", "fire hydrant", "-", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "-", "backpack", "umbrella", "-", "-", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "-", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed", "-", "dining table", "-", "-", "toilet", "-", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "-", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush", "-"
};

static const model_spec *find_model(const char *id) { for(size_t i=0;i<sizeof(models)/sizeof(models[0]);i++) if(!strcmp(models[i].id,id)) return &models[i]; return NULL; }
static void list_models(FILE *out) { for(size_t i=0;i<sizeof(models)/sizeof(models[0]);i++) fprintf(out,"%s\t%s\n",models[i].id,models[i].description); }

static int load_file(const char *path,char **doc,size_t *length) {
    FILE *f=fopen(path,"rb"); long size;
    if(!f||fseek(f,0,SEEK_END)||(size=ftell(f))<0||size>4*1024*1024||fseek(f,0,SEEK_SET)){if(f)fclose(f);return-1;}
    *doc=malloc((size_t)size+1); if(!*doc||fread(*doc,1,(size_t)size,f)!=(size_t)size){free(*doc);*doc=NULL;fclose(f);return-1;}
    fclose(f);(*doc)[size]='\0';*length=(size_t)size;return 0;
}

static int model_config(const model_spec *model,const char *share,char output[PATH_MAX]) {
    char source[PATH_MAX],wanted[PATH_MAX],*doc=NULL,*network,*end;size_t length;FILE *f=NULL;
    output[0]='\0';
    if(snprintf(source,sizeof(source),"%s/%s",share,model->config_name)<0||snprintf(wanted,sizeof(wanted),"/usr/share/imx500-models/%s",model->network)<0||load_file(source,&doc,&length)||camera_temp_path(output,PATH_MAX,model->id,".json"))goto fail;
    network=strstr(doc,"/usr/share/imx500-models/");if(!network||(end=strstr(network,".rpk"))==NULL)goto fail;end+=4;
    f=fopen(output,"wb");if(!f||fwrite(doc,1,(size_t)(network-doc),f)!=(size_t)(network-doc)||fputs(wanted,f)==EOF||fwrite(end,1,length-(size_t)(end-doc),f)!=length-(size_t)(end-doc)||fclose(f)){f=NULL;goto fail;}
    free(doc);return 0;
fail: if(f)fclose(f);if(*output)unlink(output);free(doc);return-1;
}

static int load_tensor(const char *path,double values[MAX_TENSOR_VALUES],size_t *count) {
    char *doc=NULL,*tensor,*cursor,*end;size_t length;if(load_file(path,&doc,&length))return-1;(void)length;
    tensor=strstr(doc,"\"CnnOutputTensor\"");if(!tensor||(cursor=strchr(tensor,'['))==NULL){free(doc);return-1;}cursor++;*count=0;
    while(*count<MAX_TENSOR_VALUES){while(*cursor==' '||*cursor=='\n'||*cursor=='\r'||*cursor=='\t'||*cursor==',')cursor++;if(*cursor==']')break;errno=0;values[*count]=strtod(cursor,&end);if(errno||end==cursor){free(doc);return-1;}(*count)++;cursor=end;}
    free(doc);return *count>0&&*count<MAX_TENSOR_VALUES?0:-1;
}

static int write_objects(const char *path,const double *v,size_t count,double threshold,double scale) {
    size_t n;
    unsigned found=0;
    FILE *f;
    if(count<7||(count-1)%6)return-1;
    n=(count-1)/6;
    f=fopen(path,"wb");
    if(!f||fprintf(f,"{\n  \"threshold\": %.3f,\n  \"coordinate_space\": \"normalized\",\n  \"detections\": [",threshold)<0)goto fail;
    for(size_t i=0;i<n;i++){int class_id=(int)v[n*5+i];double score=v[n*4+i];if(score<threshold||class_id<0||class_id>=100||!strcmp(classes[class_id],"-"))continue;if(found++&&fputc(',',f)==EOF)goto fail;if(fprintf(f,"\n    {\"class_id\": %d, \"label\": \"%s\", \"confidence\": %.6f, \"box\": {\"ymin\": %.6f, \"xmin\": %.6f, \"ymax\": %.6f, \"xmax\": %.6f}}",class_id,classes[class_id],score,v[i]/scale,v[n+i]/scale,v[n*2+i]/scale,v[n*3+i]/scale)<0)goto fail;}
    if(fprintf(f,"%s  ],\n  \"count\": %u\n}\n",found?"\n":"",found)<0||fclose(f))return-1;
    return 0;
fail:if(f)fclose(f);return-1;
}

static void cleanup_run(model_run *run){if(*run->image)unlink(run->image);if(*run->metadata)unlink(run->metadata);if(*run->results)unlink(run->results);}

static int execute_model(model_run *run,const char *share,double threshold) {
    const char *camera=camera_setting("ROSE_RPICAM_STILL","/usr/bin/rpicam-still");char config[PATH_MAX]="";double tensor[MAX_TENSOR_VALUES];size_t count;
    if(camera_temp_path(run->image,sizeof(run->image),run->model->id,".jpg")||camera_temp_path(run->metadata,sizeof(run->metadata),"metadata",".json")||(run->model->kind==MODEL_OBJECT&&camera_temp_path(run->results,sizeof(run->results),"detections",".json"))||model_config(run->model,share,config))goto fail;
    char *args[]={(char*)camera,"--camera","0","--rotation","180","--nopreview","--timeout","5s","--width","2028","--height","1520","--quality","93","--post-process-file",config,"--metadata",run->metadata,"--metadata-format","json","--output",run->image,NULL};
    if(camera_run(args,300)||!camera_file_ready(run->image)||!camera_file_ready(run->metadata))goto fail;
    if(run->model->kind==MODEL_OBJECT&&(load_tensor(run->metadata,tensor,&count)||write_objects(run->results,tensor,count,threshold,run->model->coordinate_scale)))goto fail;
    unlink(config);return 0;
fail:if(*config)unlink(config);cleanup_run(run);return-1;
}

int main(int argc,char **argv) {
    const char *home=camera_setting("HOME","/home/rose"),*threshold_text=camera_setting("ROSE_NYX_THRESHOLD","0.55");char share[PATH_MAX],*end;double threshold=strtod(threshold_text,&end);model_run runs[MAX_MODELS]={{0}};size_t run_count=argc>1?(size_t)(argc-1):1;
    if(argc==2&&!strcmp(argv[1],"--list")){list_models(stdout);return 0;}if(run_count>MAX_MODELS){fprintf(stderr,"at most %d models may be requested\n",MAX_MODELS);return 2;}if(end==threshold_text||*end||threshold<0||threshold>1)threshold=.55;if(snprintf(share,sizeof(share),"%s/.local/share/rose-tools/camera",home)<0)return 1;
    for(size_t i=0;i<run_count;i++){const char *id=argc>1?argv[i+1]:"object0";runs[i].model=find_model(id);if(!runs[i].model){fprintf(stderr,"unknown model '%s'; available models:\n",id);list_models(stderr);return 2;}for(size_t p=0;p<i;p++)if(runs[p].model==runs[i].model){fprintf(stderr,"duplicate model '%s'\n",id);return 2;}}
    for(size_t i=0;i<run_count;i++){fprintf(stderr,"Nyx running %s (%zu/%zu)\n",runs[i].model->id,i+1,run_count);if(execute_model(&runs[i],share,threshold)){fprintf(stderr,"Nyx model %s failed\n",runs[i].model->id);for(size_t p=0;p<i;p++)cleanup_run(&runs[p]);return 1;}}
    printf("{\"mode\":\"live-sequential\",\"runs\":[");for(size_t i=0;i<run_count;i++){if(i)putchar(',');printf("{\"model\":\"%s\",\"image\":\"%s\",",runs[i].model->id,runs[i].image);if(runs[i].model->kind==MODEL_OBJECT)printf("\"detections\":\"%s\",",runs[i].results);printf("\"metadata\":\"%s\"}",runs[i].metadata);}puts("]}");return 0;
}
