#!/usr/bin/env python3
"""
Draw a square on the screen at specified coordinates.
This creates a temporary overlay window that draws a square on the screen.
"""

import sys
import time
import subprocess
import os
import tempfile

def draw_square_on_screen(x, y, size=20, color="red", duration=2.0, display=":99"):
    """
    Draw a square on the screen at coordinates (x, y).
    
    Args:
        x: X coordinate
        y: Y coordinate  
        size: Size of the square in pixels (default: 20)
        color: Color of the square (default: "red")
        duration: How long to show the square in seconds (default: 2.0)
        display: X11 display (default: ":99")
    """
    # Set display
    os.environ['DISPLAY'] = display
    
    # Try using tkinter first (usually available)
    try:
        import tkinter as tk
        
        # Create window in a way that allows it to persist
        root = tk.Tk()
        root.overrideredirect(True)  # Remove window decorations
        root.geometry(f"{size}x{size}+{x}+{y}")
        root.attributes('-topmost', True)  # Keep on top
        
        # Try to make it a splash window (no decorations)
        try:
            root.attributes('-type', 'splash')
        except:
            pass
        
        # Create a canvas with colored square
        canvas = tk.Canvas(root, width=size, height=size, highlightthickness=0, bg='black')
        canvas.pack(fill=tk.BOTH, expand=True)
        
        # Draw the square
        if color == "red":
            fill_color = "red"
        elif color == "green":
            fill_color = "green"
        elif color == "blue":
            fill_color = "blue"
        else:
            fill_color = color
        
        canvas.create_rectangle(0, 0, size, size, fill=fill_color, outline="black", width=2)
        
        root.update()
        root.update_idletasks()
        
        # Schedule window destruction after duration using tkinter's after method
        def close_window():
            try:
                root.quit()
                root.destroy()
            except:
                pass
        
        # Schedule destruction after duration (milliseconds)
        root.after(int(duration * 1000), close_window)
        
        # Run mainloop (this will block until window is destroyed or duration expires)
        root.mainloop()
        
        return True
        
    except ImportError:
        # Fallback: Use X11 libraries if available
        try:
            from Xlib import X, display as xdisplay
            
            d = xdisplay.Display(display)
            screen = d.screen()
            root = screen.root
            
            # Create a window for drawing
            win = root.create_window(
                x, y, size, size,
                0, screen.root_depth,
                X.InputOutput,
                X.CopyFromParent,
                background_pixel=screen.white_pixel,
                event_mask=X.ExposureMask
            )
            
            # Set window attributes for overlay
            win.change_attributes(override_redirect=True)
            
            # Map the window
            win.map()
            d.sync()
            
            # Create a graphics context for drawing
            colormap = screen.default_colormap
            if color == "red":
                pixel_color = colormap.alloc_named_color("red").pixel
            else:
                pixel_color = colormap.alloc_named_color(color).pixel
            
            gc = win.create_gc(
                foreground=pixel_color,
                line_width=2
            )
            
            # Draw filled rectangle
            win.fill_rectangle(gc, 0, 0, size, size)
            
            # Draw border
            border_gc = win.create_gc(foreground=screen.black_pixel, line_width=2)
            win.rectangle(border_gc, 0, 0, size-1, size-1)
            
            d.sync()
            
            # Keep the square visible for the duration
            time.sleep(duration)
            
            # Unmap and destroy the window
            win.unmap()
            d.sync()
            win.destroy()
            d.close()
            
            return True
            
        except ImportError:
            # Final fallback: Use imagemagick and feh/xdotool
            try:
                from PIL import Image, ImageDraw
                
                # Create a small image with the square
                img = Image.new('RGB', (size, size), (0, 0, 0))
                draw = ImageDraw.Draw(img)
                
                # Draw a colored square
                if color == "red":
                    fill_color = (255, 0, 0)
                elif color == "green":
                    fill_color = (0, 255, 0)
                elif color == "blue":
                    fill_color = (0, 0, 255)
                else:
                    fill_color = (255, 0, 0)  # Default to red
                
                draw.rectangle([0, 0, size-1, size-1], fill=fill_color, outline=(0, 0, 0), width=2)
                
                # Save to temp file
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                img.save(temp_file.name)
                temp_file.close()
                
                # Try to display using feh (if available)
                try:
                    proc = subprocess.Popen(
                        ['feh', '--geometry', f'{size}x{size}+{x}+{y}', '--title', 'overlay', temp_file.name],
                        env=dict(os.environ, DISPLAY=display)
                    )
                    time.sleep(duration)
                    proc.terminate()
                    proc.wait(timeout=1)
                except FileNotFoundError:
                    # feh not available, try other methods
                    pass
                
                # Clean up temp file
                os.unlink(temp_file.name)
                
                return True
                
            except ImportError:
                print(f"WARNING: Cannot draw square - missing libraries. Install python3-tkinter, python3-xlib, or pillow")
                return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: draw-square-on-screen.py <x> <y> [size] [color] [duration] [display]")
        print("Example: draw-square-on-screen.py 100 200 30 red 2.0 :99")
        sys.exit(1)
    
    x = int(sys.argv[1])
    y = int(sys.argv[2])
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    color = sys.argv[4] if len(sys.argv) > 4 else "red"
    duration = float(sys.argv[5]) if len(sys.argv) > 5 else 2.0
    display = sys.argv[6] if len(sys.argv) > 6 else ":99"
    
    success = draw_square_on_screen(x, y, size, color, duration, display)
    sys.exit(0 if success else 1)
