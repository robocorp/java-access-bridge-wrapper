
//Usually you will require both swing and awt packages
// even if you are working with just swings.
import javax.accessibility.Accessible;
import javax.accessibility.AccessibleHypertext;
import javax.swing.*;
import javax.swing.event.HyperlinkEvent;
import javax.swing.event.HyperlinkListener;
import javax.swing.text.BadLocationException;
import javax.swing.text.Document;

import java.awt.*;
import java.awt.event.*;
import java.io.IOException;
import java.net.URISyntaxException;
import java.time.format.DateTimeFormatter;
import java.time.LocalDateTime;

class BasicSwing extends JFrame implements WindowListener, ActionListener {
    DateTimeFormatter dtf = DateTimeFormatter.ofPattern("HH:mm:ss");
    JLabel label = new JLabel();
    JEditorPane ep = new JEditorPane();
    TextField text = new TextField(20);
    String defaultText = "default text";
    JMenuBar mb;

    public static void main(String[] args) {
        BasicSwing myWindow = new BasicSwing("Chat Frame");
        myWindow.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
        myWindow.setSize(450, 450);
        myWindow.setLocation(50, 100);
        myWindow.setVisible(true);
    }

    public BasicSwing(String title) {
        super(title);
        addWindowListener(this);
        addMenus();
        JPanel panel = new JPanel();
        JButton send = new JButton("Send1");
        JButton clear = new JButton("Clear2");

        this.label.setText("Comment");
        this.label.setHorizontalTextPosition(JLabel.LEFT);
        this.label.setVerticalTextPosition(JLabel.CENTER);

        this.text.setText(defaultText);

        this.ep.setFont(this.ep.getFont().deriveFont(24.0f));
        send.addActionListener(this);
        clear.addActionListener(this);
        panel.add(send);
        panel.add(label);
        panel.add(this.text);
        panel.add(clear);

        this.ep.setContentType("text/html");
        this.ep.setEditable(false);
        this.ep.setText("<html><a href='http://www.yahoo.com'>hypertext</a></html>");

        this.ep.addHyperlinkListener(new HyperlinkListener() {
            public void hyperlinkUpdate(HyperlinkEvent e) {
                if(e.getEventType() == HyperlinkEvent.EventType.ACTIVATED) {
                    try {
                        Desktop.getDesktop().browse(e.getURL().toURI());
                    } catch (IOException | URISyntaxException exc) {
                        // exc.printStackTrace();
                    }
                }
            }
        });

        this.getContentPane().add(BorderLayout.NORTH, mb);
        this.getContentPane().add(BorderLayout.CENTER, this.ep);
        this.getContentPane().add(BorderLayout.SOUTH, panel);
    }

    public void createFrame() {
        JFrame frame = new JFrame("Exit");
        JPanel panel = new JPanel();
        JButton ok = new JButton("Exit ok");
        ok.addActionListener(this);
        JButton cancel = new JButton("Exit cancel");
        cancel.addActionListener(this);

        panel.add(ok);
        panel.add(cancel);

        frame.getContentPane().add(BorderLayout.CENTER, panel);
        frame.pack();
        frame.setAlwaysOnTop(true);
        frame.setEnabled(true);
        frame.setVisible(true);
    }

    public void addMenus() {
        mb = new JMenuBar();
        JMenu m1 = new JMenu("FILE");
        JMenu m2 = new JMenu("Help");
        mb.add(m1);
        mb.add(m2);
        JMenuItem m11 = new JMenuItem("Open");
        JMenuItem m22 = new JMenuItem("Save as");
        JMenuItem m13 = new JMenuItem("Exit");
        m13.addActionListener(this);
        m1.add(m11);
        m1.add(m22);
        m1.add(m13);
    }

    private void appendTextToEditorPane(String text) {
        try {
            Document doc = this.ep.getDocument();
            doc.insertString(doc.getLength(), text, null);
         } catch(BadLocationException exc) {
            // exc.printStackTrace();
         }
    }

    @Override
    public void actionPerformed(ActionEvent e) {
        String objText = e.getActionCommand();
        LocalDateTime now = LocalDateTime.now();
        if (objText == "Send1") {
            this.appendTextToEditorPane(dtf.format(now) + " " + text.getText() + "\n");
            this.text.setText(defaultText);
        } else if (objText == "Clear2") {
            this.text.setText(defaultText);
            this.ep.setText("");
        } else if (objText == "Exit") {
            createFrame();
        } else if (objText == "Exit ok") {
            System.exit(0);
        } else if (objText == "Exit cancel") {
            // TODO: close exit frame
        }
    }

    @Override
    public void windowOpened(WindowEvent arg0) {
    }

    @Override
    public void windowClosing(WindowEvent arg0) {
        System.exit(0);
    }

    @Override
    public void windowClosed(WindowEvent arg0) {
    }

    @Override
    public void windowIconified(WindowEvent arg0) {
    }

    @Override
    public void windowDeiconified(WindowEvent arg0) {
    }

    @Override
    public void windowActivated(WindowEvent arg0) {
    }

    @Override
    public void windowDeactivated(WindowEvent arg0) {
    }
}
