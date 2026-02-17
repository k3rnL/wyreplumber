cmake_minimum_required(VERSION 4.1)
project(pypewire C)

set(CMAKE_C_STANDARD 11)

find_package(Python3 REQUIRED COMPONENTS Development)
find_package(PkgConfig REQUIRED)
pkg_check_modules(PIPEWIRE REQUIRED libpipewire-0.3)
pkg_check_modules(WIREPLUMBER REQUIRED wireplumber-0.4)

add_library(wyreplumber_core MODULE
        native/wyreplumber/wyreplumber.c
        native/wyreplumber/wp_connection/wp_connection.c
        native/wyreplumber/wp_connection/wp_connection.h
        native/wyreplumber/wp_connection/get_nodes.c
        native/wyreplumber/wp_connection/get_modules.c
        native/wyreplumber/wp_connection/get_metadata.c
        native/wyreplumber/wp_connection/load_module.c
        native/wyreplumber/wp_connection/sync.c
        native/wyreplumber/wp_node/wp_node.c
        native/wyreplumber/wp_module/wp_module.h
        native/wyreplumber/wp_module/wp_module.c
        native/wyreplumber/wp_port/wp_port.c
        native/wyreplumber/wp_metadata/wp_metadata.c
        native/wyreplumber/wp_metadata/metadata_find.c
        native/wyreplumber/wp_metadata/metadata_set.c
        native/wyreplumber/wp_metadata/metadata_clear.c
        native/wyreplumber/wp_metadata/metadata_iterate.c)


target_include_directories(wyreplumber_core PRIVATE
        ${Python3_INCLUDE_DIRS}
        ${PIPEWIRE_INCLUDE_DIRS}
        ${WIREPLUMBER_INCLUDE_DIRS}
        src/native
)

target_compile_options(wyreplumber_core PRIVATE
        ${PIPEWIRE_CFLAGS_OTHER}
        ${WIREPLUMBER_CFLAGS_OTHER}
)

target_link_directories(wyreplumber_core PRIVATE
        ${PIPEWIRE_LIBRARY_DIRS}
        ${WIREPLUMBER_LIBRARY_DIRS}
)

target_link_libraries(wyreplumber_core PRIVATE
        Python3::Python
        ${PIPEWIRE_LIBRARIES}
        ${WIREPLUMBER_LIBRARIES}
)