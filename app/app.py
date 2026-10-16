import dearpygui.dearpygui as dpg
from helpers import (init_dpg, load_gds, init_plots, create_table,
                     init_sim_menu, save_project, load_project)

if __name__ == "__main__":
    dpg.create_context()

    with dpg.font_registry():
        with dpg.font("DejaVuSans.ttf", 20) as default_font:
            dpg.bind_font(default_font)

    with dpg.window(tag="Primary Window"):
        # main window of the app
        with dpg.collapsing_header(label="Main Options", default_open=True):
            # importing/generating files
            with dpg.group(horizontal=True):
                dpg.add_text("GDS file:")
                dpg.add_input_text(default_value="",
                                   tag='filepath', width=240)
                dpg.add_button(label="LOAD", callback=load_gds, tag="load_gds")
                dpg.add_text("project dir:")
                dpg.add_input_text(default_value="",
                                   tag='save_path', width=240)
                dpg.add_button(label="GENERATE", callback=save_project, tag="generate")
                dpg.add_button(label="LOAD", callback=load_project, tag="load")
                dpg.add_text("", tag='filepath_info')

            with dpg.file_dialog(directory_selector=False, show=False, callback=None,
                                 height=int(400), width=int(800), tag='file_dialog'):
                dpg.add_file_extension(".csv")

        with dpg.collapsing_header(label="Structure Preview", default_open=True):
            # cross-section plots
            init_plots()

        with dpg.collapsing_header(label="Structure Volumes", default_open=True):
            # structure definition menu
            create_table()

        with dpg.collapsing_header(label="Simulation", default_open=True):
            # simulation definition menu
            with dpg.child_window(height=200, autosize_x=True):
                init_sim_menu()

    init_dpg()