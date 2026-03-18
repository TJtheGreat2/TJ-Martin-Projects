import javax.swing.JFrame;

public class Gameframe extends JFrame{
Gameframe(){

   GamePanel panel = new GamePanel();
    this.add(panel);
    this.setTitle("Snake");
    this.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
    this.setResizable(false);
    this.pack();
    this.setVisible(true);
    this.setLocationRelativeTo(null);
}
}