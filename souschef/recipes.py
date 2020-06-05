

dispatch = {
    1: {
        1: {
            "func": _set_classifiers,
            "args": {
                "value": "pan_on_off,pasta"
            }
        }
    },
    2: {
        1: {
            "func": _update_screen,
            "args": {
                "message": "Place a pan on the hob to start"
            },
        },
        2: {
            "func": _set_hob_off
        },
        3: {
            "func": _classify,
            "args": {
                "model": "pan_on_off",
                "label": "pan_on"
            }
        },
        4: {
            "func": _classify,
            "args": {
                "model": "pasta",
                "label": "empty_pan"
            }
        },
        5: {
            "func": _set_fixed_setpoint,
            "args": {
                "value": 50
            }
        },
    },
}