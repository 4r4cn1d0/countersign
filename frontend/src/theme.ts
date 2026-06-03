import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#2f6fed",
      dark: "#1f4faf"
    },
    secondary: {
      main: "#0f8a77"
    },
    error: {
      main: "#c83349"
    },
    warning: {
      main: "#b06b00"
    },
    success: {
      main: "#2f8f46"
    },
    background: {
      default: "#f6f8fb",
      paper: "#ffffff"
    },
    text: {
      primary: "#172033",
      secondary: "#5c6778"
    }
  },
  shape: {
    borderRadius: 8
  },
  typography: {
    fontFamily: "'Inter', 'SF Pro Display', 'Segoe UI', sans-serif",
    h5: {
      fontWeight: 700
    },
    h6: {
      fontWeight: 700
    },
    button: {
      fontWeight: 700,
      textTransform: "none"
    }
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          minHeight: 38
        }
      }
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          fontWeight: 600
        }
      }
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none"
        }
      }
    }
  }
});
