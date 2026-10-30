// Build/contract harness for the MIT-licensed Luau release 501.
#include "Luau/Compiler.h"
#include "lua.h"
#include "lualib.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
static std::string read(const char* p) {std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("Cannot open input");return std::string(std::istreambuf_iterator<char>(f),{});}
static void run(lua_State* L,const std::string& b,int results) {if(luau_load(L,"@LuxBlox-compat",b.data(),b.size(),0)||lua_pcall(L,0,results,0))throw std::runtime_error(lua_tostring(L,-1));}
int main(int argc,char** argv) {
 try {
  if(argc<3)return 2;Luau::CompileOptions o;o.optimizationLevel=0;o.debugLevel=0;
  if(std::string(argv[1])=="compile") {std::string b=Luau::compile(read(argv[2]),o);if(b.empty()||b[0]!=1)throw std::runtime_error("Compile error or unsupported version");std::cout.write(b.data(),b.size());return 0;}
  if(argc!=5)return 2;lua_State* L=luaL_newstate();luaL_openlibs(L);
  run(L,Luau::compile(read(argv[3]),o),0);run(L,read(argv[2]),1);lua_setglobal(L,"_result");run(L,Luau::compile(read(argv[4]),o),0);lua_close(L);return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
