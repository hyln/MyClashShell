# MCS

基于clash core构建，能够帮你自动配置命令行版本的clash并提供简单的使用方法，无需图形化界面支持，方便一些没有图形化界面的嵌入式设备使用。

[Quickstart](./doc/quick_start.md)

```                            
                    SS                   88        
                    8@88                8          
                   :8@ %8                  8      
                   S88   S   88888         8                
                   8X     8                     
                  :8S                       8   
                  8S8   8@                                  
                  8S8  88@8           8      8  
                  8%                         8      
                 %@@          8888           8      
                 S8@                                        
                 8X8                          @             
          X88   :;8S  
        X88     XXX8  SS%   SS% 8X8%888S @@X    X8%
       %S8      8@88  SS%   SS% 88S      @88    8%@
       888      8@88  SSS888SSS 8SX8@8%; @8S    SS8
        8@S    @8S8   SX%   SX% 8SX      @88    S88
         @@8@X8SS8    SS8   SS8 88S8@@88 XS88@8 88888@ 
           8XS8t8
```                            
     
## 常用命令

```
myclash #查看当前myclcash状态
myclash service update_subcribe # 更新订阅
myclash change_subscribe <订阅名>  # 手动切换订阅(不下载新文件)

myclash shell on 
myclash shell off

myclash window off
myclash window on

```