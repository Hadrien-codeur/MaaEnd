cmake_minimum_required(VERSION 3.21)
project(fixed_zipline_tests LANGUAGES CXX)
enable_testing()
add_executable(fixed-zipline-tests fixed_zipline_tests.cpp)
target_compile_features(fixed-zipline-tests PRIVATE cxx_std_20)
target_include_directories(fixed-zipline-tests PRIVATE
    ../../../agent/cpp-algo/source
    ../../../agent/cpp-algo/MaaUtils/include)
if(MSVC)
    target_compile_options(fixed-zipline-tests PRIVATE /utf-8 /EHsc)
endif()
add_test(NAME fixed-zipline-contract COMMAND fixed-zipline-tests
    ${CMAKE_CURRENT_SOURCE_DIR}/../../../assets/data/MapNavigator/fixed_zipline_routes.json)
