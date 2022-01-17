
//Usually you will require both swing and awt packages
// even if you are working with just swings.
import javax.accessibility.Accessible;
import javax.swing.*;
import javax.swing.table.DefaultTableModel;

import java.awt.*;
import java.awt.event.*;
import java.time.format.DateTimeFormatter;
import java.util.Vector;
import java.time.LocalDateTime;

class BasicSwing extends JFrame implements WindowListener, ActionListener, ItemListener {
    DateTimeFormatter dtf = DateTimeFormatter.ofPattern("HH:mm:ss");
    TextField text = new TextField(20);
    String defaultText = "default text";
    JMenuBar mb;
    JTextArea ta;
    JComboBox comboBox;

    public static void main(String[] args) {
        BasicSwing myWindow = new BasicSwing("Chat Frame");
        myWindow.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
        myWindow.setSize(800, 350);
        myWindow.setLocation(50, 100);
        myWindow.setVisible(true);
    }

    public BasicSwing(String title) {
        super(title);
        addWindowListener(this);
        addMenus();
        JPanel taButtonPanel = new JPanel();
        JButton send = new JButton("Send1");
        JButton clear = new JButton("Clear2");

        JLabel label = new JLabel();
        label.setText("Comment");
        label.setHorizontalTextPosition(JLabel.LEFT);
        label.setVerticalTextPosition(JLabel.CENTER);

        text.setText(defaultText);
        ta = new JTextArea();
        ta.setFont(ta.getFont().deriveFont(24.0f));
        send.addActionListener(this);
        clear.addActionListener(this);
        taButtonPanel.add(send);
        taButtonPanel.add(label);
        taButtonPanel.add(text);
        taButtonPanel.add(clear);

        ExampleTableModel tableModel = new ExampleTableModel();
        tableModel.addRow(new Object[]{"Cell11", "Cell12", true});
        tableModel.addRow(new Object[]{"Cell21", "Cell22", false});
        tableModel.addRow(new Object[]{"Cell31", "Cell32", false});
        JTable table = new JTable(tableModel);
        table.setFillsViewportHeight(true);

        String comboBoxOptions[] = { "Hello", "World" };
        this.comboBox = new JComboBox(comboBoxOptions);
        this.comboBox.addItemListener(this);

        JPanel leftPanel = new JPanel(new GridLayout(2, 1));
        leftPanel.add(new JScrollPane(table));
        leftPanel.add(this.comboBox);

        JPanel rightPanel = new JPanel(new GridLayout(2, 1));
        rightPanel.add(ta);
        rightPanel.add(taButtonPanel);

        JPanel contextPanel = new JPanel(new GridLayout(1, 2));
        contextPanel.add(leftPanel);
        contextPanel.add(rightPanel);

        this.getContentPane().add(BorderLayout.NORTH, mb);
        this.getContentPane().add(BorderLayout.CENTER, contextPanel);
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

    @Override
    public void actionPerformed(ActionEvent e) {
        Object obj = e.getSource();
        String objText = e.getActionCommand();
        LocalDateTime now = LocalDateTime.now();
        if (objText == "Send1") {
            ta.append(dtf.format(now) + " " + text.getText() + "\n");
            text.setText(defaultText);
        } else if (objText == "Clear2") {
            text.setText(defaultText);
            ta.setText("");
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

    public void itemStateChanged(ItemEvent e)
    {
        // if the state combobox is changed
        if (e.getSource() == this.comboBox) {
            ta.append(this.comboBox.getSelectedItem() + "\n");
        }
    }

    public class ExampleTableModel extends DefaultTableModel {
        private int editableColumn = 2;

        public ExampleTableModel() {
          super(new String[]{"Column1", "Column2", "Checkbox"}, 0);
        }

        @Override
        public Class getColumnClass(int column) {
            switch (column) {
                case 0:
                    return String.class;
                case 1:
                    return String.class;
                case 2:
                    return Boolean.class;
                default:
                    return Boolean.class;
            }
        }

        @Override
        public boolean isCellEditable(int row, int column) {
            if (column == this.editableColumn) {
                System.out.println("Is editable column");
                return true;
            }
            return false;
        }

        @Override
        public void setValueAt(Object aValue, int row, int column) {
            if (aValue instanceof Boolean && column == this.editableColumn) {
                System.out.println(aValue);
                Vector rowData = (Vector)getDataVector().get(row);
                rowData.set(this.editableColumn, (boolean)aValue);
                fireTableCellUpdated(row, column);
            }
        }
    }
}
